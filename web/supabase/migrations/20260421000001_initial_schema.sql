-- =============================================================
-- Phase 1: Initial Schema
-- Financial Chatbot Web App
-- =============================================================
-- Tables:
--   projects, project_members, report_uploads, report_sheet_metadata,
--   normalized_financial_rows, financial_type_map, heading_map,
--   heading_aliases, discrepancies, query_logs, admin_mapping_uploads
-- =============================================================

-- Enable pgcrypto for gen_random_uuid() (already available in Supabase)
-- No additional extensions needed beyond what Supabase provides by default.

-- ─────────────────────────────────────────────────────────────
-- Helper: auto-update updated_at column
-- ─────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ─────────────────────────────────────────────────────────────
-- projects
-- ─────────────────────────────────────────────────────────────
-- A project is identified by BOTH project_code and project_name together
-- (per PRD §6.2A). The combination must be unique.
CREATE TABLE projects (
  id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  project_code   TEXT        NOT NULL,
  project_name   TEXT        NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT projects_code_name_unique UNIQUE (project_code, project_name)
);

CREATE TRIGGER set_projects_updated_at
  BEFORE UPDATE ON projects
  FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE INDEX idx_projects_code ON projects (project_code);

-- ─────────────────────────────────────────────────────────────
-- project_members
-- ─────────────────────────────────────────────────────────────
-- Links Clerk user IDs to projects with a role.
-- Roles: 'member' (read/query), 'admin' (full access incl. mapping uploads).
CREATE TABLE project_members (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id  UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id     TEXT        NOT NULL,  -- Clerk user ID (e.g. user_abc123)
  role        TEXT        NOT NULL DEFAULT 'member'
                          CHECK (role IN ('member', 'admin')),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT project_members_project_user_unique UNIQUE (project_id, user_id)
);

CREATE INDEX idx_project_members_user  ON project_members (user_id);
CREATE INDEX idx_project_members_proj  ON project_members (project_id);

-- ─────────────────────────────────────────────────────────────
-- report_uploads
-- ─────────────────────────────────────────────────────────────
-- One row per uploaded Excel report. Supports activation/validation lifecycle.
--
-- validation_status:
--   'pending'  → ingestion not yet started
--   'valid'    → fully mapped and usable
--   'partial'  → some rows unmapped; usable with warnings
--   'invalid'  → critical structure missing; not usable
--
-- is_active: true means this upload is the active source of truth for its
--   project + report_month + report_year (latest validated upload wins,
--   per PRD §16.3). Only one upload per (project_id, report_month, report_year)
--   can be active at a time (enforced via a partial unique index below).
CREATE TABLE report_uploads (
  id                            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id                    UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  report_month                  SMALLINT    NOT NULL CHECK (report_month BETWEEN 1 AND 12),
  report_year                   SMALLINT    NOT NULL CHECK (report_year > 2000),
  storage_path                  TEXT        NOT NULL,  -- Supabase Storage path
  original_filename             TEXT        NOT NULL,
  uploaded_by                   TEXT        NOT NULL,  -- Clerk user ID
  upload_timestamp              TIMESTAMPTZ NOT NULL DEFAULT now(),
  validation_status             TEXT        NOT NULL DEFAULT 'pending'
                                            CHECK (validation_status IN ('pending','valid','partial','invalid')),
  is_active                     BOOLEAN     NOT NULL DEFAULT false,
  unmapped_heading_count        INT         NOT NULL DEFAULT 0,
  unmapped_financial_type_count INT         NOT NULL DEFAULT 0,
  overlap_count                 INT         NOT NULL DEFAULT 0,
  ingestion_error               TEXT,
  created_at                    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at                    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER set_report_uploads_updated_at
  BEFORE UPDATE ON report_uploads
  FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- Only one active upload per project+period
CREATE UNIQUE INDEX idx_report_uploads_one_active
  ON report_uploads (project_id, report_month, report_year)
  WHERE is_active = true;

CREATE INDEX idx_report_uploads_project        ON report_uploads (project_id);
CREATE INDEX idx_report_uploads_project_period ON report_uploads (project_id, report_month, report_year);
CREATE INDEX idx_report_uploads_status         ON report_uploads (validation_status);

-- ─────────────────────────────────────────────────────────────
-- report_sheet_metadata
-- ─────────────────────────────────────────────────────────────
-- Tracks parse results per sheet within a single uploaded workbook.
-- sheet_name examples: 'Financial Status', 'Projection', 'Committed Cost',
--   'Accrual', 'Cash Flow' (per PRD §5.3).
--
-- parse_status:
--   'pending' → not yet parsed
--   'ok'      → parsed cleanly
--   'partial' → parsed with unmapped items
--   'error'   → could not parse
--   'skipped' → sheet not present in workbook
CREATE TABLE report_sheet_metadata (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  upload_id         UUID        NOT NULL REFERENCES report_uploads(id) ON DELETE CASCADE,
  sheet_name        TEXT        NOT NULL,
  row_count         INT,
  mapped_row_count  INT,
  unmapped_row_count INT,
  parse_status      TEXT        NOT NULL DEFAULT 'pending'
                    CHECK (parse_status IN ('pending','ok','partial','error','skipped')),
  parse_error       TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT report_sheet_metadata_upload_sheet_unique UNIQUE (upload_id, sheet_name)
);

CREATE INDEX idx_sheet_meta_upload ON report_sheet_metadata (upload_id);

-- ─────────────────────────────────────────────────────────────
-- normalized_financial_rows
-- ─────────────────────────────────────────────────────────────
-- The core normalized data store. Each row is one extracted financial value
-- with full traceability back to its source workbook cell (for verbose mode).
--
-- Active-truth rule (PRD §16.3): when a later validated upload supersedes
-- an earlier one for the same project/sheet/month/year/item_code/financial_type,
-- is_active on older rows is set to false and superseded_by_upload_id is set.
-- The older rows are retained for audit and discrepancy comparison.
CREATE TABLE normalized_financial_rows (
  id                     UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  upload_id              UUID        NOT NULL REFERENCES report_uploads(id) ON DELETE CASCADE,
  project_id             UUID        NOT NULL REFERENCES projects(id)       ON DELETE CASCADE,
  sheet_name             TEXT        NOT NULL,
  report_month           SMALLINT    NOT NULL CHECK (report_month BETWEEN 1 AND 12),
  report_year            SMALLINT    NOT NULL CHECK (report_year > 2000),

  -- Financial type resolution
  raw_financial_type     TEXT,
  financial_type         TEXT,       -- canonical clean name from financial_type_map

  -- Heading resolution
  item_code              TEXT,
  data_type              TEXT,       -- canonical data_type from heading_map
  friendly_name          TEXT,       -- official Friendly_Name (PRD §6.2E)
  category               TEXT,       -- 'Income', 'Cost', etc.
  tier                   SMALLINT,   -- hierarchy level

  -- The value
  value                  NUMERIC,

  -- Verbose-mode traceability (PRD §12.2)
  source_row_number      INT,        -- Excel row number in source sheet
  source_cell_reference  TEXT,       -- e.g. 'C15'

  -- Active-truth tracking (PRD §16.3–16.4)
  is_active              BOOLEAN     NOT NULL DEFAULT true,
  superseded_by_upload_id UUID       REFERENCES report_uploads(id),

  created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Primary query path: project + sheet + period
CREATE INDEX idx_nfr_project_sheet_period
  ON normalized_financial_rows (project_id, sheet_name, report_month, report_year);

-- Active-row filter
CREATE INDEX idx_nfr_active
  ON normalized_financial_rows (project_id, is_active)
  WHERE is_active = true;

-- Item-level lookups
CREATE INDEX idx_nfr_item_code      ON normalized_financial_rows (item_code);
CREATE INDEX idx_nfr_financial_type ON normalized_financial_rows (financial_type);
CREATE INDEX idx_nfr_upload         ON normalized_financial_rows (upload_id);

-- Overlap detection: find all rows for same project/sheet/period/item/type
CREATE INDEX idx_nfr_overlap_key
  ON normalized_financial_rows (project_id, sheet_name, report_month, report_year, item_code, financial_type);

-- ─────────────────────────────────────────────────────────────
-- financial_type_map
-- ─────────────────────────────────────────────────────────────
-- Admin-maintained mapping: raw financial type strings from Excel
-- → canonical clean financial type names (PRD §5.2A).
-- Loaded from financial_type_map.csv uploads.
-- acronyms: array of lowercase acronyms/synonyms for query resolution.
CREATE TABLE financial_type_map (
  id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  raw_financial_type   TEXT        NOT NULL UNIQUE,
  clean_financial_type TEXT        NOT NULL,
  acronyms             TEXT[]      NOT NULL DEFAULT '{}',
  is_active            BOOLEAN     NOT NULL DEFAULT true,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER set_financial_type_map_updated_at
  BEFORE UPDATE ON financial_type_map
  FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE INDEX idx_ftm_clean    ON financial_type_map (clean_financial_type);
CREATE INDEX idx_ftm_active   ON financial_type_map (is_active) WHERE is_active = true;
-- GIN index for acronym array lookups
CREATE INDEX idx_ftm_acronyms ON financial_type_map USING GIN (acronyms);

-- ─────────────────────────────────────────────────────────────
-- heading_map
-- ─────────────────────────────────────────────────────────────
-- Admin-maintained mapping: item codes → canonical data types and metadata
-- (PRD §5.2B). Loaded from construction_headings_enriched.csv uploads.
-- Friendly_Name is the official display name used in query results.
CREATE TABLE heading_map (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  item_code     TEXT        NOT NULL UNIQUE,
  data_type     TEXT        NOT NULL,
  friendly_name TEXT        NOT NULL,
  category      TEXT,       -- 'Income', 'Cost', etc.
  tier          SMALLINT,   -- hierarchy level (1 = top, higher = deeper)
  is_active     BOOLEAN     NOT NULL DEFAULT true,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER set_heading_map_updated_at
  BEFORE UPDATE ON heading_map
  FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE INDEX idx_hm_data_type     ON heading_map (data_type);
CREATE INDEX idx_hm_category_tier ON heading_map (category, tier);
CREATE INDEX idx_hm_active        ON heading_map (is_active) WHERE is_active = true;
-- Support hierarchy traversal (e.g. item_code LIKE '2.2%')
CREATE INDEX idx_hm_item_code_prefix ON heading_map (item_code text_pattern_ops);

-- ─────────────────────────────────────────────────────────────
-- heading_aliases
-- ─────────────────────────────────────────────────────────────
-- Additional aliases (acronyms, shorthand, synonyms) for each heading_map entry.
-- Used during query resolution to expand user input to canonical item codes.
-- alias_type: 'acronym', 'synonym', 'shorthand'
CREATE TABLE heading_aliases (
  id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  heading_map_id UUID        NOT NULL REFERENCES heading_map(id) ON DELETE CASCADE,
  alias          TEXT        NOT NULL,
  alias_type     TEXT        NOT NULL DEFAULT 'acronym'
                             CHECK (alias_type IN ('acronym','synonym','shorthand')),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT heading_aliases_map_alias_unique UNIQUE (heading_map_id, alias)
);

CREATE INDEX idx_ha_alias          ON heading_aliases (alias);
CREATE INDEX idx_ha_heading_map_id ON heading_aliases (heading_map_id);

-- ─────────────────────────────────────────────────────────────
-- discrepancies
-- ─────────────────────────────────────────────────────────────
-- Records detected differences when overlapping monthly movement data
-- across uploads has changed values (PRD §16.4).
-- The latest validated upload's value is the active truth; the prior
-- value is retained here for audit. Admins review and close these.
--
-- review_status: 'pending', 'reviewed', 'dismissed'
CREATE TABLE discrepancies (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id      UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  sheet_name      TEXT        NOT NULL,
  report_month    SMALLINT    NOT NULL CHECK (report_month BETWEEN 1 AND 12),
  report_year     SMALLINT    NOT NULL CHECK (report_year > 2000),
  item_code       TEXT,
  data_type       TEXT,
  old_value       NUMERIC,
  new_value       NUMERIC,
  old_upload_id   UUID        NOT NULL REFERENCES report_uploads(id),
  new_upload_id   UUID        NOT NULL REFERENCES report_uploads(id),
  detected_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  review_status   TEXT        NOT NULL DEFAULT 'pending'
                              CHECK (review_status IN ('pending','reviewed','dismissed')),
  reviewed_by     TEXT,       -- Clerk user ID
  reviewed_at     TIMESTAMPTZ,
  reviewer_note   TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER set_discrepancies_updated_at
  BEFORE UPDATE ON discrepancies
  FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- Admin review workflow index
CREATE INDEX idx_disc_project_status ON discrepancies (project_id, review_status);
CREATE INDEX idx_disc_new_upload      ON discrepancies (new_upload_id);
CREATE INDEX idx_disc_old_upload      ON discrepancies (old_upload_id);
-- Overlap detection key: same natural key pair
CREATE INDEX idx_disc_overlap_key
  ON discrepancies (project_id, sheet_name, report_month, report_year, item_code);

-- ─────────────────────────────────────────────────────────────
-- query_logs
-- ─────────────────────────────────────────────────────────────
-- Audit trail of every chatbot query. Supports verbose mode traceability
-- and future analytics on query patterns (PRD §12.2, FR-033).
--
-- mode: 'standard' or 'verbose'
-- response_type: 'value', 'table', 'trend', 'compare', 'total', 'detail',
--   'risk', 'cash_flow', 'list', 'ambiguity', 'missing', 'error'
CREATE TABLE query_logs (
  id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id              UUID        REFERENCES projects(id) ON DELETE SET NULL,
  user_id                 TEXT        NOT NULL,  -- Clerk user ID
  raw_query               TEXT        NOT NULL,

  -- Resolved parameters
  resolved_sheet_name     TEXT,
  resolved_financial_type TEXT,
  resolved_data_type      TEXT,
  resolved_item_code      TEXT,
  resolved_month          SMALLINT,
  resolved_year           SMALLINT,
  resolved_shortcut       TEXT,

  -- Ambiguity handling
  interpretation_options  JSONB,      -- ranked options shown when ambiguous
  selected_option_index   SMALLINT,   -- index of option user chose (0-based)
  was_ambiguous           BOOLEAN     NOT NULL DEFAULT false,

  -- Response metadata
  mode                    TEXT        NOT NULL DEFAULT 'standard'
                          CHECK (mode IN ('standard','verbose')),
  response_type           TEXT,
  execution_ms            INT,

  created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_ql_project_user ON query_logs (project_id, user_id);
CREATE INDEX idx_ql_user         ON query_logs (user_id);
CREATE INDEX idx_ql_created_at   ON query_logs (created_at DESC);

-- ─────────────────────────────────────────────────────────────
-- admin_mapping_uploads
-- ─────────────────────────────────────────────────────────────
-- History of admin CSV mapping file uploads (PRD §18.1, §18.3).
-- mapping_type: 'financial_type_map' or 'heading_map'
-- Once applied, the relevant mapping table is refreshed from this file.
CREATE TABLE admin_mapping_uploads (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  mapping_type      TEXT        NOT NULL
                    CHECK (mapping_type IN ('financial_type_map','heading_map')),
  storage_path      TEXT        NOT NULL,  -- Supabase Storage path
  original_filename TEXT        NOT NULL,
  uploaded_by       TEXT        NOT NULL,  -- Clerk user ID
  upload_timestamp  TIMESTAMPTZ NOT NULL DEFAULT now(),
  validation_status TEXT        NOT NULL DEFAULT 'pending'
                    CHECK (validation_status IN ('pending','valid','invalid')),
  row_count         INT,
  error_message     TEXT,
  is_applied        BOOLEAN     NOT NULL DEFAULT false,
  applied_at        TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_amu_type       ON admin_mapping_uploads (mapping_type);
CREATE INDEX idx_amu_is_applied ON admin_mapping_uploads (is_applied);

-- =============================================================
-- ROW LEVEL SECURITY
-- =============================================================
-- RLS is enabled on all tables. The Python ingestion worker and Next.js
-- server actions must use the Supabase SERVICE ROLE key (bypasses RLS).
-- The browser client uses the Clerk JWT → Supabase JWT integration;
-- auth.jwt() ->> 'sub' returns the Clerk user ID string.
--
-- Reference: Clerk + Supabase JWT integration:
--   https://clerk.com/docs/integrations/databases/supabase
-- =============================================================

ALTER TABLE projects              ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_members       ENABLE ROW LEVEL SECURITY;
ALTER TABLE report_uploads        ENABLE ROW LEVEL SECURITY;
ALTER TABLE report_sheet_metadata ENABLE ROW LEVEL SECURITY;
ALTER TABLE normalized_financial_rows ENABLE ROW LEVEL SECURITY;
ALTER TABLE financial_type_map    ENABLE ROW LEVEL SECURITY;
ALTER TABLE heading_map           ENABLE ROW LEVEL SECURITY;
ALTER TABLE heading_aliases       ENABLE ROW LEVEL SECURITY;
ALTER TABLE discrepancies         ENABLE ROW LEVEL SECURITY;
ALTER TABLE query_logs            ENABLE ROW LEVEL SECURITY;
ALTER TABLE admin_mapping_uploads ENABLE ROW LEVEL SECURITY;

-- ─────────────────────────────────────────────────────────────
-- Helper: is the current JWT user a member of this project?
-- ─────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION is_project_member(p_project_id UUID)
RETURNS BOOLEAN AS $$
  SELECT EXISTS (
    SELECT 1 FROM project_members
    WHERE project_id = p_project_id
      AND user_id = (auth.jwt() ->> 'sub')
  );
$$ LANGUAGE sql SECURITY DEFINER STABLE;

-- ─────────────────────────────────────────────────────────────
-- Helper: is the current JWT user an admin of this project?
-- ─────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION is_project_admin(p_project_id UUID)
RETURNS BOOLEAN AS $$
  SELECT EXISTS (
    SELECT 1 FROM project_members
    WHERE project_id = p_project_id
      AND user_id = (auth.jwt() ->> 'sub')
      AND role = 'admin'
  );
$$ LANGUAGE sql SECURITY DEFINER STABLE;

-- ─────────────────────────────────────────────────────────────
-- projects: members can read their projects
-- ─────────────────────────────────────────────────────────────
CREATE POLICY "projects_select_member"
  ON projects FOR SELECT
  USING (is_project_member(id));

-- ─────────────────────────────────────────────────────────────
-- project_members: members can see their own record;
--   admins can see all members of their projects
-- ─────────────────────────────────────────────────────────────
CREATE POLICY "project_members_select_self"
  ON project_members FOR SELECT
  USING (
    user_id = (auth.jwt() ->> 'sub')
    OR is_project_admin(project_id)
  );

-- ─────────────────────────────────────────────────────────────
-- report_uploads: project members can read
-- ─────────────────────────────────────────────────────────────
CREATE POLICY "report_uploads_select_member"
  ON report_uploads FOR SELECT
  USING (is_project_member(project_id));

-- ─────────────────────────────────────────────────────────────
-- report_sheet_metadata: project members can read
-- ─────────────────────────────────────────────────────────────
CREATE POLICY "report_sheet_metadata_select_member"
  ON report_sheet_metadata FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM report_uploads ru
      WHERE ru.id = upload_id
        AND is_project_member(ru.project_id)
    )
  );

-- ─────────────────────────────────────────────────────────────
-- normalized_financial_rows: project members can read active rows
-- ─────────────────────────────────────────────────────────────
CREATE POLICY "nfr_select_member"
  ON normalized_financial_rows FOR SELECT
  USING (is_project_member(project_id));

-- ─────────────────────────────────────────────────────────────
-- financial_type_map and heading_map: all authenticated users can read
-- (these are shared reference tables; writes only via service role)
-- ─────────────────────────────────────────────────────────────
CREATE POLICY "ftm_select_authenticated"
  ON financial_type_map FOR SELECT
  USING (auth.jwt() IS NOT NULL);

CREATE POLICY "hm_select_authenticated"
  ON heading_map FOR SELECT
  USING (auth.jwt() IS NOT NULL);

CREATE POLICY "ha_select_authenticated"
  ON heading_aliases FOR SELECT
  USING (auth.jwt() IS NOT NULL);

-- ─────────────────────────────────────────────────────────────
-- discrepancies: project members can read; project admins can update
-- ─────────────────────────────────────────────────────────────
CREATE POLICY "disc_select_member"
  ON discrepancies FOR SELECT
  USING (is_project_member(project_id));

CREATE POLICY "disc_update_admin"
  ON discrepancies FOR UPDATE
  USING (is_project_admin(project_id));

-- ─────────────────────────────────────────────────────────────
-- query_logs: users can insert their own; read own logs
-- ─────────────────────────────────────────────────────────────
CREATE POLICY "ql_insert_self"
  ON query_logs FOR INSERT
  WITH CHECK (user_id = (auth.jwt() ->> 'sub'));

CREATE POLICY "ql_select_self"
  ON query_logs FOR SELECT
  USING (
    user_id = (auth.jwt() ->> 'sub')
    OR (project_id IS NOT NULL AND is_project_admin(project_id))
  );

-- ─────────────────────────────────────────────────────────────
-- admin_mapping_uploads: any authenticated user can read history;
-- inserts only via service role (admin uploads go through server action)
-- ─────────────────────────────────────────────────────────────
CREATE POLICY "amu_select_authenticated"
  ON admin_mapping_uploads FOR SELECT
  USING (auth.jwt() IS NOT NULL);
