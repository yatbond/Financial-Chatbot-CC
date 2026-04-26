-- =============================================================
-- Fix unmapped financial_type_map and heading_map entries
-- Covers all item codes and financial types found in the
-- standard Chun Wo construction financial report format.
-- =============================================================

-- ─── financial_type_map: 8 raw strings not in seed ────────────────────────────
INSERT INTO financial_type_map (raw_financial_type, clean_financial_type, acronyms) VALUES
  ('Budget 1st Working Budget',             'Working Budget',    ARRAY['wb','working budget','1wb','1st working budget']),
  ('Budget Adjustment Cost/variation',      'Budget Adjustment', ARRAY['ba','budget adj','budget adjustment']),
  ('Budget Revision as at',                 'Budget Revision',   ARRAY['br','budget rev','budget revision']),
  ('Audit Report (WIP)',                    'WIP',               ARRAY['wip','audit report','ar wip']),
  ('Projection as at',                      'Projection',        ARRAY['proj','projection','projected']),
  ('Committed Value / Cost as at',          'Committed Cost',    ARRAY['committed','cc','committed cost']),
  ('Accrual ' || chr(10) || '(Before Retention) as at', 'Accrual', ARRAY['accrual','acr']),
  ('Cash Flow Actual received & paid as at','Cash Flow',         ARRAY['cf','cash flow','cashflow'])
ON CONFLICT (raw_financial_type) DO UPDATE
  SET clean_financial_type = EXCLUDED.clean_financial_type,
      acronyms              = EXCLUDED.acronyms,
      updated_at            = now();

-- ─── heading_map: fix item 4 (seed labelled it Overhead; it's Reconciliation) ─
UPDATE heading_map
SET data_type     = 'Reconciliation',
    friendly_name = 'Reconciliation',
    category      = NULL,
    updated_at    = now()
WHERE item_code = '4';

-- ─── heading_map: add all 68 missing item codes ────────────────────────────────
INSERT INTO heading_map (item_code, data_type, friendly_name, category, tier) VALUES

  -- Income Tier 2 (1.13–1.17 not in seed)
  ('1.13',   'LD Deduction',        'Less: Liquidated Damages',               'Income', 2),
  ('1.14',   'Retention Deduction', 'Less: Retention Money',                  'Income', 2),
  ('1.15',   'NSC Retention',       'Less: Retention Money (NSC)',             'Income', 2),
  ('1.16',   'Partialing Income',   'Partialing Income Total',                 'Income', 2),
  ('1.17',   'Advance Payment Inc', 'Advance Payment (Income)',                'Income', 2),

  -- Income Tier 3
  ('1.2.2',  'CE Fee',              'Fee of Contractual Entitlement',          'Income', 3),
  ('1.12.2', 'Pain Gain Sharing',   'Pain Gain Sharing',                       'Income', 3),
  ('1.12.3', 'Stretch Target Inc',  'Stretch Target Income',                   'Income', 3),

  -- Preliminaries Tier 3 (2.1.x)
  ('2.1.1',  'Mgmt Manpower',       'Manpower (Mgt. & Supervision)',           'Cost', 3),
  ('2.1.2',  'RE Manpower',         'Manpower (RE)',                           'Cost', 3),
  ('2.1.3',  'Labour Manpower',     'Manpower (Labour)',                       'Cost', 3),
  ('2.1.4',  'Adm Insurance Bond',  'Adm. Cost (Insurance & Bond)',            'Cost', 3),
  ('2.1.5',  'Adm Others',          'Adm. Cost Others',                        'Cost', 3),
  ('2.1.6',  'Adm Financial Cost',  'Adm. Cost Financial Cost',                'Cost', 3),
  ('2.1.7',  'Adm Messing',         'Adm. Cost Messing',                       'Cost', 3),
  ('2.1.8',  'DSC Prelim',          'DSC (Preliminaries)',                      'Cost', 3),
  ('2.1.9',  'General Material',    'General Material',                        'Cost', 3),
  ('2.1.10', 'Plant Prelim',        'Plant (Preliminaries)',                    'Cost', 3),
  ('2.1.11', 'JV Mgmt Fee',         'JV Partner Management Fee',               'Cost', 3),
  ('2.1.12', 'Potential Sav Prel',  'Potential Savings (Preliminaries)',        'Cost', 3),
  ('2.1.13', 'HO Consultant',       'Manpower (HO-Consultant)',                 'Cost', 3),
  ('2.1.14', 'Adm Levies',          'Adm. Cost (Levies)',                       'Cost', 3),

  -- Materials Tier 3 (2.2.x) — 2.2.15 already in seed
  ('2.2.1',  'Concrete',            'Concrete',                                'Cost', 3),
  ('2.2.2',  'Reinforcement',       'Reinforcement',                            'Cost', 3),
  ('2.2.3',  'Tile Granite Marble', 'Tile, Granite & Marble',                  'Cost', 3),
  ('2.2.4',  'Temp Work Steel',     'Temporary Work (Steel & Sheet Piles)',     'Cost', 3),
  ('2.2.5',  'Structural Steel',    'Structural Steel Member',                  'Cost', 3),
  ('2.2.6',  'Furniture',           'Furniture',                               'Cost', 3),
  ('2.2.7',  'Sanitary Fitting',    'Sanitary Fitting',                        'Cost', 3),
  ('2.2.8',  'Ironmongery',         'Ironmongery',                             'Cost', 3),
  ('2.2.9',  'MVAC',                'MVAC',                                    'Cost', 3),
  ('2.2.10', 'Electrical',          'Electrical',                              'Cost', 3),
  ('2.2.11', 'PD Material',         'P&D',                                     'Cost', 3),
  ('2.2.12', 'FS Material',         'FS',                                      'Cost', 3),
  ('2.2.13', 'Other Material',      'Others Material Cost',                    'Cost', 3),
  ('2.2.14', 'Deposit',             'Deposit',                                 'Cost', 3),
  ('2.2.16', 'Concrete Tunnel',     'Concrete (for Tunnel)',                    'Cost', 3),
  ('2.2.17', 'Rebar Tunnel',        'Reinforcement (for Tunnel)',               'Cost', 3),
  ('2.2.18', 'PD Tunnel',           'P&D Material (for Tunnel)',                'Cost', 3),

  -- Plant & Machinery Tier 3 (2.3.x)
  ('2.3.1',  'Plant Purchased',     'Plant & Tools (Purchased)',                'Cost', 3),
  ('2.3.2',  'Plant External Hire', 'Plant & Tools (External Hire)',            'Cost', 3),
  ('2.3.3',  'Diesel Lubricant',    'Diesel & Lubricant',                      'Cost', 3),
  ('2.3.4',  'Plant Repair',        'Repairing',                               'Cost', 3),
  ('2.3.5',  'Plant Resale',        'Resale',                                  'Cost', 3),
  ('2.3.6',  'Other Plant',         'Others Plant & Machinery',                'Cost', 3),
  ('2.3.7',  'Depreciation',        'Depreciation (in Ledger)',                'Cost', 3),
  ('2.3.8',  'Potential Sav Plant', 'Potential Savings (Plants)',               'Cost', 3),
  ('2.3.9',  'Plant Internal Hire', 'Plant & Tools (Internal Hire)',            'Cost', 3),

  -- DSC / Subcontractor Tier 3 (2.4.x) — 2.4.4 and 2.4.7 already in seed
  ('2.4.1',  'DSC Contract Works',  'DSC Contract Works',                      'Cost', 3),
  ('2.4.2',  'DSC Variation',       'DSC Variation',                            'Cost', 3),
  ('2.4.3',  'DSC Claim',           'DSC Claim',                               'Cost', 3),
  ('2.4.5',  'DSC Down Payment',    'DSC Down Payment',                         'Cost', 3),
  ('2.4.6',  'DSC Retention',       'DSC Retention',                            'Cost', 3),
  ('2.4.8',  'DSC Commercial Sett', 'DSC Commercial Settlement',               'Cost', 3),
  ('2.4.9',  'DSC Tunnel Works',    'DSC Contract Works (for Tunnel)',          'Cost', 3),

  -- Nominated Package Tier 3 (2.6.x)
  ('2.6.1',  'NSC Cost',            'Nominated Subcontractor Cost',             'Cost', 3),
  ('2.6.2',  'NS Supplier Cost',    'Nominated Supplier Cost',                  'Cost', 3),

  -- Incentive / POR Bonus Tier 3 (2.11.x)
  ('2.11.1', 'Bonus Cost Saving',   'Cost Saving Related Bonus',               'Cost', 3),
  ('2.11.2', 'Bonus Non Cost',      'Non-Cost Saving Related Bonus',            'Cost', 3),
  ('2.11.3', 'Cost Saving Ach',     'Cost Saving Achieved',                    'Cost', 3),

  -- Reconciliation sub-items (4.x)
  ('4.1',    'Internal Interest',   'Internal Interest',                        NULL,   2),
  ('4.3',    'Total Adjustment',    'Total Adjustment',                         NULL,   2),

  -- Overhead section (6.x) — maps to the Excel items numbered 6.0, 6.1, etc.
  ('6',      'Overhead',            'Overhead',                                 NULL,   1),
  ('6.1',    'HO Overhead Rate',    'HO Overhead Rate %',                       NULL,   2),
  ('6.1.1',  'HO Overhead Amt',     'HO Overhead Amount',                       NULL,   3),
  ('6.1.2',  'BU Overhead Amt',     'BU Overhead Amount',                       NULL,   3),
  ('6.2',    'Acc Profit BF',       'Accumulated Profit/(Loss) B/F',            NULL,   2),

  -- Accumulated Net Profit (7.x)
  ('7',      'Net Profit',          'Accumulated Net Profit/(Loss)',             NULL,   1)

ON CONFLICT (item_code) DO UPDATE
  SET data_type     = EXCLUDED.data_type,
      friendly_name = EXCLUDED.friendly_name,
      category      = EXCLUDED.category,
      tier          = EXCLUDED.tier,
      updated_at    = now();

-- ─── Backfill existing normalized_financial_rows ──────────────────────────────
-- Fill financial_type where it was NULL (raw string now has a mapping)
UPDATE normalized_financial_rows nfr
SET financial_type = ftm.clean_financial_type
FROM financial_type_map ftm
WHERE nfr.raw_financial_type = ftm.raw_financial_type
  AND nfr.financial_type IS NULL;

-- Fill data_type / friendly_name / category / tier where NULL (item code now mapped)
UPDATE normalized_financial_rows nfr
SET data_type     = hm.data_type,
    friendly_name = hm.friendly_name,
    category      = hm.category,
    tier          = hm.tier
FROM heading_map hm
WHERE nfr.item_code = hm.item_code
  AND (nfr.data_type IS NULL OR nfr.friendly_name IS NULL)
  AND hm.is_active = true;

-- ─── Promote partial uploads to valid ────────────────────────────────────────
-- Any upload that was 'partial' and now has no NULL-mapped rows becomes 'valid'
UPDATE report_uploads ru
SET validation_status             = 'valid',
    unmapped_heading_count        = 0,
    unmapped_financial_type_count = 0,
    updated_at                    = now()
WHERE ru.validation_status = 'partial'
  AND NOT EXISTS (
    SELECT 1
    FROM normalized_financial_rows nfr
    WHERE nfr.upload_id = ru.id
      AND (nfr.financial_type IS NULL OR nfr.data_type IS NULL)
  );
