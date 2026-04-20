# Data Model

Phase 1 — Database Schema and Core Domain Model

Migration file: `web/supabase/migrations/20260421000001_initial_schema.sql`
TypeScript types: `web/lib/types/database.ts`
Seed data: `web/supabase/seed.sql`

---

## Table Summary

| Table | Purpose |
|-------|---------|
| `projects` | One row per construction project (code + name) |
| `project_members` | Links Clerk user IDs to projects with a role |
| `report_uploads` | One row per uploaded Excel report with ingestion lifecycle state |
| `report_sheet_metadata` | Parse results per sheet per upload |
| `normalized_financial_rows` | Core extracted data with full verbose-mode traceability |
| `financial_type_map` | Admin-maintained: raw financial type → canonical clean name |
| `heading_map` | Admin-maintained: item code → canonical data type + hierarchy |
| `heading_aliases` | Additional aliases for query resolution |
| `discrepancies` | Detected value conflicts across overlapping monthly uploads |
| `query_logs` | Audit trail of all chatbot queries |
| `admin_mapping_uploads` | History of admin CSV mapping file uploads |

---

## Entity Relationships

```
projects
  ├─ project_members (project_id → projects.id)
  ├─ report_uploads  (project_id → projects.id)
  │    └─ report_sheet_metadata (upload_id → report_uploads.id)
  │    └─ normalized_financial_rows (upload_id → report_uploads.id)
  ├─ discrepancies   (project_id → projects.id)
  │    ├─ old_upload_id → report_uploads.id
  │    └─ new_upload_id → report_uploads.id
  └─ query_logs      (project_id → projects.id)

heading_map
  └─ heading_aliases (heading_map_id → heading_map.id)

financial_type_map   (standalone reference table)
admin_mapping_uploads (standalone audit table)
```

---

## Key Design Decisions

### Project identity uses both code and name
A unique constraint on `(project_code, project_name)` enforces the PRD requirement
that both fields together form the project identity. Neither alone is sufficient.

### Active-truth rule for overlapping monthly data
When a later validated upload supersedes an earlier one for the same
`(project_id, sheet_name, report_month, report_year, item_code, financial_type)`:
- The older `normalized_financial_rows` rows have `is_active = false` and
  `superseded_by_upload_id` set.
- The new rows have `is_active = true`.
- A `discrepancies` record is created if the values differ.
- Only one upload can be `is_active = true` per `(project_id, report_month, report_year)`
  (enforced by a partial unique index).

### Verbose mode traceability
`normalized_financial_rows` stores `source_row_number` (Excel row) and
`source_cell_reference` (e.g. `C15`) from the Python ingestion worker.
These are surfaced in verbose mode per PRD §12.2.

### Snapshot vs time-series distinction
The `sheet_name` column drives this distinction:
- `'Financial Status'` = snapshot mode (one report month, no trend history)
- `'Projection'`, `'Committed Cost'`, `'Accrual'`, `'Cash Flow'` = time-series mode

The query resolution engine uses this to apply the correct access rules.

### Query resolution uses acronyms in two places
- `financial_type_map.acronyms` (array, GIN-indexed) for financial type matching
- `heading_aliases` (separate table) for item code / data type matching

Both are populated by admin CSV uploads and seeded with representative data.

---

## Row Level Security Approach

All tables have RLS enabled. Two helper functions drive the policies:

```sql
is_project_member(project_id UUID) → boolean
is_project_admin(project_id UUID)  → boolean
```

Both functions read `project_members` and compare against `auth.jwt() ->> 'sub'`,
which is the Clerk user ID from the JWT.

| Table | SELECT | INSERT | UPDATE | DELETE |
|-------|--------|--------|--------|--------|
| `projects` | project member | — | — | — |
| `project_members` | own row or admin | — | — | — |
| `report_uploads` | project member | — | — | — |
| `report_sheet_metadata` | project member (via upload) | — | — | — |
| `normalized_financial_rows` | project member | — | — | — |
| `financial_type_map` | any authenticated | — | — | — |
| `heading_map` | any authenticated | — | — | — |
| `heading_aliases` | any authenticated | — | — | — |
| `discrepancies` | project member | — | project admin | — |
| `query_logs` | own or project admin | own | — | — |
| `admin_mapping_uploads` | any authenticated | — | — | — |

**Writes to most tables go through the service role key** used by:
- Python ingestion worker (insert normalized rows, flag discrepancies, activate uploads)
- Next.js server actions (upload trigger, mapping application, report activation)

The Clerk + Supabase JWT integration doc:
https://clerk.com/docs/integrations/databases/supabase

---

## Seed Data

`web/supabase/seed.sql` populates:
- `financial_type_map` with the 9 standard financial type mappings from the PRD
- `heading_map` with the full construction financial hierarchy (item codes 1–5, tiers 1–3)
- `heading_aliases` with common acronyms (gp, prelim, dsc, vo, etc.)

In production, these are maintained via admin CSV uploads. The seed provides a
working starting point for local development and testing.

---

## Validation Status Lifecycle

```
report_uploads.validation_status:
  pending → valid | partial | invalid

report_uploads.is_active:
  false (on insert)
  → true (set by ingestion worker after validation_status = valid | partial)
  → false (when superseded by a newer upload for same project+period)
```

---

## Applying the Schema

### Option A: Supabase CLI (recommended)
```bash
cd web
npx supabase db push          # push migration to linked project
npx supabase db seed          # apply seed data
```

### Option B: Direct SQL
```bash
psql $SUPABASE_DB_URL -f supabase/migrations/20260421000001_initial_schema.sql
psql $SUPABASE_DB_URL -f supabase/seed.sql
```

### Option C: Supabase Dashboard
Copy and paste each file into the SQL Editor in your Supabase project dashboard.
Run migration first, then seed.
