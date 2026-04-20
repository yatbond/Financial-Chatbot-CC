-- =============================================================
-- Seed Data: financial_type_map and heading_map
-- Financial Chatbot Web App
-- =============================================================
-- This seed file populates the two admin-maintained mapping tables
-- with representative starting data based on PRD §5.2 and §8.
--
-- In production these tables are managed by admin CSV uploads
-- (admin_mapping_uploads workflow). This seed provides a functional
-- starting point for local development and testing.
--
-- To apply:
--   supabase db seed   (via Supabase CLI)
-- OR run against your DB directly:
--   psql $DATABASE_URL -f seed.sql
-- =============================================================

-- ─────────────────────────────────────────────────────────────
-- financial_type_map
-- Maps raw financial type strings found in Excel workbooks to
-- canonical clean names, with acronyms for query resolution.
-- ─────────────────────────────────────────────────────────────
INSERT INTO financial_type_map (raw_financial_type, clean_financial_type, acronyms) VALUES
  ('Budget Tender',        'Budget Tender',      ARRAY['bt','budget tender']),
  ('Business Plan',        'Business Plan',      ARRAY['bp','business plan']),
  ('WIP',                  'WIP',                ARRAY['wip','work in progress']),
  ('Projection',           'Projection',         ARRAY['proj','projection','projected']),
  ('Committed Cost',       'Committed Cost',     ARRAY['committed','cc','committed cost']),
  ('Accrual',              'Accrual',            ARRAY['accrual','acr']),
  ('Cash Flow',            'Cash Flow',          ARRAY['cf','cash flow','cashflow']),
  ('Latest Budget',        'Latest Budget',      ARRAY['lb','latest budget']),
  ('Revision',             'Revision',           ARRAY['rev','revision'])
ON CONFLICT (raw_financial_type) DO UPDATE
  SET clean_financial_type = EXCLUDED.clean_financial_type,
      acronyms = EXCLUDED.acronyms,
      updated_at = now();

-- ─────────────────────────────────────────────────────────────
-- heading_map
-- Maps item codes to canonical data types with hierarchy metadata.
-- Item codes follow the construction financial report hierarchy:
--   1.x   = Income items
--   2.x   = Cost items
--   3     = Gross Profit
--   4     = Overhead
--   5     = Gross Profit after Recon & Overhead
-- ─────────────────────────────────────────────────────────────
INSERT INTO heading_map (item_code, data_type, friendly_name, category, tier) VALUES
  -- Income (Tier 1 top-level)
  ('1',       'Total Income',        'Total Income',                          'Income', 1),

  -- Income sub-items (Tier 2)
  ('1.1',     'Contract Sum',        'Contract Sum',                          'Income', 2),
  ('1.2',     'Variation',           'Variation / Claim',                     'Income', 2),
  ('1.3',     'Nominated Sub',       'Nominated Sub-contractor Income',       'Income', 2),
  ('1.4',     'Domestic Sub',        'Domestic Sub-contractor Income',        'Income', 2),
  ('1.5',     'Specialist',          'Specialist Income',                     'Income', 2),
  ('1.6',     'Material Supply',     'Material Supply Income',                'Income', 2),
  ('1.7',     'Claims',              'Claims',                                'Income', 2),
  ('1.8',     'CPF',                 'CPF',                                   'Income', 2),
  ('1.9',     'Fluctuation',         'Fluctuation',                           'Income', 2),
  ('1.10',    'Retention',           'Retention',                             'Income', 2),
  ('1.11',    'Advance Payment',     'Advance Payment',                       'Income', 2),
  ('1.12',    'Other Revenue',       'Other Revenue',                         'Income', 2),

  -- Income sub-sub-items (Tier 3)
  ('1.2.1',   'VO/CE',               'Variation Order / Contractual Entitlement', 'Income', 3),
  ('1.12.1',  'Other Revenue Items', 'Other Revenue Items',                   'Income', 3),

  -- Cost (Tier 1 top-level)
  ('2',       'Total Cost',          'Total Cost',                            'Cost',   1),

  -- Cost sub-items (Tier 2)
  ('2.1',     'Preliminaries',       'Preliminaries',                         'Cost',   2),
  ('2.2',     'Materials',           'Materials',                             'Cost',   2),
  ('2.3',     'Plant',               'Plant',                                 'Cost',   2),
  ('2.4',     'DSC',                 'Domestic Sub-contractor Cost',          'Cost',   2),
  ('2.5',     'NSC',                 'Nominated Sub-contractor Cost',         'Cost',   2),
  ('2.6',     'Labour',              'Labour',                                'Cost',   2),
  ('2.7',     'Contingencies',       'Allow for Contingencies',               'Cost',   2),
  ('2.8',     'Rectifications',      'Allow for Rectification Works',         'Cost',   2),
  ('2.9',     'Specialist Cost',     'Specialist Cost',                       'Cost',   2),
  ('2.10',    'Head Office OH',      'Head Office Overhead',                  'Cost',   2),
  ('2.11',    'Site OH',             'Site Overhead',                         'Cost',   2),
  ('2.12',    'Insurances',          'Insurances',                            'Cost',   2),
  ('2.13',    'Bonds',               'Bonds',                                 'Cost',   2),
  ('2.14',    'Stretch Target',      'Stretch Target (Cost)',                  'Cost',   2),

  -- Cost sub-sub-items (Tier 3) — risk-sensitive per PRD §13.10
  ('2.2.15',  'Potential Savings M', 'Potential Savings (Materials)',          'Cost',   3),
  ('2.4.4',   'Contra Charge',       'Contra Charge',                         'Cost',   3),
  ('2.4.7',   'Potential Savings D', 'Potential Savings (DSC)',                'Cost',   3),

  -- Gross Profit (Tier 1)
  ('3',       'Gross Profit',        'Gross Profit',                          NULL,     1),

  -- Overhead (Tier 1)
  ('4',       'Overhead',            'Overhead',                              NULL,     1),

  -- Gross Profit after Recon & Overhead (Tier 1) — used in Cash Flow shortcut
  ('5',       'GP After Overhead',   'Gross Profit (after Recon & Overhead)', NULL,     1)

ON CONFLICT (item_code) DO UPDATE
  SET data_type     = EXCLUDED.data_type,
      friendly_name = EXCLUDED.friendly_name,
      category      = EXCLUDED.category,
      tier          = EXCLUDED.tier,
      updated_at    = now();

-- ─────────────────────────────────────────────────────────────
-- heading_aliases
-- Common acronyms and shorthands for query resolution.
-- ─────────────────────────────────────────────────────────────
INSERT INTO heading_aliases (heading_map_id, alias, alias_type)
SELECT hm.id, alias.alias, alias.alias_type
FROM heading_map hm
JOIN (VALUES
  ('1',      'income',      'synonym'),
  ('2',      'cost',        'synonym'),
  ('2.1',    'prelim',      'acronym'),
  ('2.1',    'preliminaries', 'synonym'),
  ('2.2',    'mat',         'acronym'),
  ('2.3',    'plant',       'synonym'),
  ('2.4',    'dsc',         'acronym'),
  ('2.4',    'sub',         'shorthand'),
  ('2.5',    'nsc',         'acronym'),
  ('3',      'gp',          'acronym'),
  ('3',      'gross profit','synonym'),
  ('5',      'gp after',    'shorthand'),
  ('1.2.1',  'vo',          'acronym'),
  ('1.2.1',  'ce',          'acronym'),
  ('1.7',    'claims',      'synonym'),
  ('1.8',    'cpf',         'acronym')
) AS alias (item_code, alias, alias_type) ON hm.item_code = alias.item_code
ON CONFLICT (heading_map_id, alias) DO NOTHING;
