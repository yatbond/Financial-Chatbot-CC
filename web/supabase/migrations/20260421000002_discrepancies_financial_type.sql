-- Migration: add financial_type column to discrepancies
-- Needed by Phase 6 overlap detection (PRD §16.5 "financial concept" field).
-- The overlap key in normalized_financial_rows includes financial_type,
-- so discrepancy records must capture it for admin review in Phase 11.

ALTER TABLE discrepancies
  ADD COLUMN financial_type TEXT;

-- Rebuild overlap key index to include financial_type
DROP INDEX IF EXISTS idx_disc_overlap_key;
CREATE INDEX idx_disc_overlap_key
  ON discrepancies (project_id, sheet_name, report_month, report_year, item_code, financial_type);
