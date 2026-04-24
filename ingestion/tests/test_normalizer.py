"""Integration tests for normalizer.py — no DB or file I/O required."""
from __future__ import annotations

import pytest

from src.normalizer import NormalizeResult, normalize_rows
from src.parser import ExtractedRow


# ── Fixtures ──────────────────────────────────────────────────────────────────

FINANCIAL_TYPE_MAP = {
    "Projection as at":                         "Projection",
    "Committed Value / Cost as at":             "Committed Cost",
    "Accrual \n(Before Retention) as at":       "Accrual",
    "Cash Flow Actual received & paid as at":   "Cash Flow",
    "Audit Report (WIP)":                       "WIP",
    "Business Plan":                            "Business Plan",
    "Budget Revision as at":                    "Latest Budget",
    "Budget Tender":                            "Budget Tender",
}

HEADING_MAP = {
    "1":   {"data_type": "Income",       "friendly_name": "Total Income",    "category": "Income",  "tier": 1},
    "2.1": {"data_type": "Less Cost",    "friendly_name": "Preliminaries",   "category": "Cost",    "tier": 2},
    "3":   {"data_type": "Gross Profit", "friendly_name": "Gross Profit",    "category": "Summary", "tier": 1},
}


def _row(
    item_code: str | None = "1",
    raw_ft: str = "Projection as at",
    value: float | None = 100_000.0,
    sheet_name: str = "Financial Status",
    month: int = 2,
    year: int = 2026,
    row_num: int = 15,
) -> ExtractedRow:
    return ExtractedRow(
        sheet_name=sheet_name,
        item_code=item_code,
        trade="Test Trade",
        raw_financial_type=raw_ft,
        value=value,
        report_month=month,
        report_year=year,
        source_row_number=row_num,
        source_col=2,
        source_cell_ref=f"C{row_num}",
    )


UPLOAD_ID = "upload-abc-123"
PROJECT_ID = "proj-abc-456"


# ── Mapped rows ───────────────────────────────────────────────────────────────

class TestNormalizeRowsMapped:
    def test_all_required_output_keys_present(self):
        result = normalize_rows([_row()], UPLOAD_ID, PROJECT_ID, FINANCIAL_TYPE_MAP, HEADING_MAP)
        row = result.rows[0]
        required = {
            "upload_id", "project_id", "sheet_name", "report_month", "report_year",
            "raw_financial_type", "financial_type", "item_code",
            "data_type", "friendly_name", "category", "tier",
            "value", "source_row_number", "source_cell_reference",
        }
        assert required.issubset(row.keys())

    def test_mapped_financial_type_resolved(self):
        result = normalize_rows([_row(raw_ft="Projection as at")], UPLOAD_ID, PROJECT_ID, FINANCIAL_TYPE_MAP, HEADING_MAP)
        assert result.rows[0]["financial_type"] == "Projection"

    def test_mapped_item_code_resolves_heading(self):
        result = normalize_rows([_row(item_code="2.1")], UPLOAD_ID, PROJECT_ID, FINANCIAL_TYPE_MAP, HEADING_MAP)
        row = result.rows[0]
        assert row["data_type"] == "Less Cost"
        assert row["friendly_name"] == "Preliminaries"
        assert row["tier"] == 2
        assert row["category"] == "Cost"

    def test_upload_and_project_ids_set(self):
        result = normalize_rows([_row()], UPLOAD_ID, PROJECT_ID, FINANCIAL_TYPE_MAP, HEADING_MAP)
        assert result.rows[0]["upload_id"] == UPLOAD_ID
        assert result.rows[0]["project_id"] == PROJECT_ID

    def test_source_fields_passed_through(self):
        result = normalize_rows([_row(row_num=42)], UPLOAD_ID, PROJECT_ID, FINANCIAL_TYPE_MAP, HEADING_MAP)
        assert result.rows[0]["source_row_number"] == 42
        assert result.rows[0]["source_cell_reference"] == "C42"

    def test_zero_value_preserved(self):
        result = normalize_rows([_row(value=0.0)], UPLOAD_ID, PROJECT_ID, FINANCIAL_TYPE_MAP, HEADING_MAP)
        assert result.rows[0]["value"] == 0.0
        assert result.rows[0]["value"] is not None

    def test_none_value_preserved(self):
        result = normalize_rows([_row(value=None)], UPLOAD_ID, PROJECT_ID, FINANCIAL_TYPE_MAP, HEADING_MAP)
        assert result.rows[0]["value"] is None

    def test_empty_input_produces_empty_output(self):
        result = normalize_rows([], UPLOAD_ID, PROJECT_ID, FINANCIAL_TYPE_MAP, HEADING_MAP)
        assert result.rows == []
        assert result.unmapped_financial_types == set()
        assert result.unmapped_item_codes == set()

    def test_sheet_name_and_period_preserved(self):
        result = normalize_rows(
            [_row(sheet_name="Projection", month=3, year=2025)],
            UPLOAD_ID, PROJECT_ID, FINANCIAL_TYPE_MAP, HEADING_MAP,
        )
        row = result.rows[0]
        assert row["sheet_name"] == "Projection"
        assert row["report_month"] == 3
        assert row["report_year"] == 2025

    def test_raw_financial_type_preserved(self):
        result = normalize_rows([_row(raw_ft="Projection as at")], UPLOAD_ID, PROJECT_ID, FINANCIAL_TYPE_MAP, HEADING_MAP)
        assert result.rows[0]["raw_financial_type"] == "Projection as at"


# ── Unmapped rows ─────────────────────────────────────────────────────────────

class TestNormalizeRowsUnmapped:
    def test_unknown_financial_type_tracked(self):
        result = normalize_rows(
            [_row(raw_ft="Some Unknown FT")], UPLOAD_ID, PROJECT_ID, FINANCIAL_TYPE_MAP, HEADING_MAP
        )
        assert "Some Unknown FT" in result.unmapped_financial_types
        assert result.rows[0]["financial_type"] is None

    def test_unknown_item_code_tracked(self):
        result = normalize_rows(
            [_row(item_code="9.9.9")], UPLOAD_ID, PROJECT_ID, FINANCIAL_TYPE_MAP, HEADING_MAP
        )
        assert "9.9.9" in result.unmapped_item_codes
        assert result.rows[0]["data_type"] is None
        assert result.rows[0]["friendly_name"] is None
        assert result.rows[0]["tier"] is None

    def test_none_item_code_not_tracked_as_unmapped(self):
        """Rows with no item code (summary rows) must not pollute the unmapped set."""
        result = normalize_rows(
            [_row(item_code=None)], UPLOAD_ID, PROJECT_ID, FINANCIAL_TYPE_MAP, HEADING_MAP
        )
        assert result.unmapped_item_codes == set()

    def test_multiple_rows_accumulate_unmapped(self):
        rows = [
            _row(raw_ft="Type A", item_code="99"),
            _row(raw_ft="Type B", item_code="98"),
        ]
        result = normalize_rows(rows, UPLOAD_ID, PROJECT_ID, FINANCIAL_TYPE_MAP, HEADING_MAP)
        assert "Type A" in result.unmapped_financial_types
        assert "Type B" in result.unmapped_financial_types
        assert "99" in result.unmapped_item_codes
        assert "98" in result.unmapped_item_codes

    def test_same_unknown_type_not_duplicated_in_set(self):
        rows = [_row(raw_ft="Unknown"), _row(raw_ft="Unknown")]
        result = normalize_rows(rows, UPLOAD_ID, PROJECT_ID, FINANCIAL_TYPE_MAP, HEADING_MAP)
        assert result.unmapped_financial_types == {"Unknown"}

    def test_output_row_count_matches_input_row_count(self):
        rows = [_row(), _row(item_code="2.1"), _row(item_code=None)]
        result = normalize_rows(rows, UPLOAD_ID, PROJECT_ID, FINANCIAL_TYPE_MAP, HEADING_MAP)
        assert len(result.rows) == 3
