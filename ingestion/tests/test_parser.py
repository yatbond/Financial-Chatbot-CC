"""Unit tests for parser.py — no DB or file I/O required."""

import pytest

from src.parser import (
    ExtractedRow,
    FS_DATA_START,
    FS_VALUE_COLUMNS,
    MONTHLY_DATA_START,
    MONTHLY_RAW_TYPE,
    _month_year,
    cell_ref,
    col_letter,
    extract_report_header,
    normalize_item_code,
    parse_financial_status,
    parse_monthly_sheet,
)


# ── normalize_item_code ───────────────────────────────────────────────────────

class TestNormalizeItemCode:
    def test_none_returns_none(self):
        assert normalize_item_code(None) is None

    def test_integer_float(self):
        assert normalize_item_code(1.0) == "1"
        assert normalize_item_code(2.0) == "2"

    def test_decimal_float(self):
        assert normalize_item_code(1.1) == "1.1"
        assert normalize_item_code(2.12) == "2.12"

    def test_no_float_artefacts(self):
        # 0.1 + 0.2 == 0.30000000000000004 in pure float — make sure we strip zeros
        result = normalize_item_code(1.1)
        assert "0000" not in result

    def test_string_passthrough(self):
        assert normalize_item_code("3.1") == "3.1"
        assert normalize_item_code("A01") == "A01"

    def test_empty_string_returns_none(self):
        assert normalize_item_code("") is None
        assert normalize_item_code("   ") is None


# ── col_letter / cell_ref ─────────────────────────────────────────────────────

class TestCellRef:
    def test_col_letter_a(self):
        assert col_letter(0) == "A"

    def test_col_letter_z(self):
        assert col_letter(25) == "Z"

    def test_col_letter_aa(self):
        assert col_letter(26) == "AA"

    def test_cell_ref_format(self):
        # row_idx=0 → row 1, col_idx=2 → "C"
        assert cell_ref(0, 2) == "C1"
        assert cell_ref(16, 2) == "C17"
        assert cell_ref(14, 9) == "J15"


# ── _month_year ───────────────────────────────────────────────────────────────

class TestMonthYear:
    # Report in Apr–Dec (report_month >= 4)
    def test_report_in_april_apr_column(self):
        assert _month_year(4, 4, 2025) == 2025

    def test_report_in_july_dec_column(self):
        assert _month_year(12, 7, 2025) == 2025

    def test_report_in_july_jan_column(self):
        # Jan is in the *next* calendar year for an Apr-based FY
        assert _month_year(1, 7, 2025) == 2026

    def test_report_in_july_mar_column(self):
        assert _month_year(3, 7, 2025) == 2026

    # Report in Jan–Mar (report_month < 4)
    def test_report_in_feb_apr_column(self):
        # Apr-Dec belong to report_year-1
        assert _month_year(4, 2, 2026) == 2025

    def test_report_in_feb_dec_column(self):
        assert _month_year(12, 2, 2026) == 2025

    def test_report_in_feb_jan_column(self):
        assert _month_year(1, 2, 2026) == 2026

    def test_report_in_feb_mar_column(self):
        assert _month_year(3, 2, 2026) == 2026


# ── extract_report_header ─────────────────────────────────────────────────────

def _make_header_rows(
    project_code="P001",
    project_name="Test Project",
    report_date="2026-02-28",
) -> list[list]:
    rows = [[None]] * 11
    rows[2] = ["Project Code:", project_code]
    rows[3] = ["Project Name:", project_name]
    rows[4] = ["Report Date:", report_date]
    return rows


class TestExtractReportHeader:
    def test_basic_extraction(self):
        rows = _make_header_rows()
        h = extract_report_header(rows)
        assert h.project_code == "P001"
        assert h.project_name == "Test Project"
        assert h.report_month == 2
        assert h.report_year == 2026

    def test_missing_fields(self):
        h = extract_report_header([[None]] * 11)
        assert h.project_code is None
        assert h.report_date is None

    def test_date_formats(self):
        for date_str in ("2026-02-28", "28/02/2026", "28-02-2026"):
            rows = _make_header_rows(report_date=date_str)
            h = extract_report_header(rows)
            assert h.report_month == 2
            assert h.report_year == 2026, f"Failed for format: {date_str}"


# ── parse_financial_status ────────────────────────────────────────────────────

def _make_fs_rows(data_rows: list[list]) -> list[list]:
    """Pad with blank rows up to FS_DATA_START, then append data rows."""
    rows = [[None]] * FS_DATA_START
    rows.extend(data_rows)
    return rows


class TestParseFinancialStatus:
    def test_basic_row_extraction(self):
        # One data row with item_code=1.0, trade="Concrete", budget_tender=100.0
        data = [[1.0, "Concrete"] + [None] * 13]
        data[0][2] = 100.0  # col 2 = "Budget Tender"
        rows = _make_fs_rows(data)
        result = parse_financial_status(rows, report_month=2, report_year=2026)

        assert result.error is None
        budget_tender_rows = [r for r in result.rows if r.raw_financial_type == "Budget Tender"]
        assert len(budget_tender_rows) == 1
        r = budget_tender_rows[0]
        assert r.item_code == "1"
        assert r.trade == "Concrete"
        assert r.value == 100.0
        assert r.report_month == 2
        assert r.report_year == 2026

    def test_skips_blank_item_code(self):
        data = [[None, "Some Trade"] + [0.0] * 13]
        rows = _make_fs_rows(data)
        result = parse_financial_status(rows, 2, 2026)
        assert result.rows == []

    def test_none_value_preserved(self):
        data = [[1.0, "Trade"] + [None] * 13]
        rows = _make_fs_rows(data)
        result = parse_financial_status(rows, 2, 2026)
        budget_rows = [r for r in result.rows if r.raw_financial_type == "Budget Tender"]
        assert budget_rows[0].value is None

    def test_source_cell_ref(self):
        data = [[1.0, "Trade"] + [None] * 13]
        data[0][2] = 50.0
        rows = _make_fs_rows(data)
        result = parse_financial_status(rows, 2, 2026)
        r = next(r for r in result.rows if r.raw_financial_type == "Budget Tender")
        # row_idx = FS_DATA_START (0-indexed) → Excel row FS_DATA_START+1
        expected_row = FS_DATA_START + 1
        assert r.source_cell_ref == f"C{expected_row}"
        assert r.source_row_number == expected_row


# ── parse_monthly_sheet ───────────────────────────────────────────────────────

def _make_monthly_rows(month_abbrevs: list[str], data_rows: list[list]) -> list[list]:
    """Build rows with header row at index 11 containing month abbreviations starting col 2."""
    rows = [[None]] * 12  # rows 0..11
    header = [None, None] + month_abbrevs
    rows[11] = header  # METADATA_HEADER_ROWS = 11
    rows.extend(data_rows)
    return rows


class TestParseMonthlySheet:
    def test_projection_basic(self):
        # Single data row, single month column (Feb at col 2)
        data = [[1.0, "Trade", 200.0]]
        rows = _make_monthly_rows(["Feb"], data)
        result = parse_monthly_sheet(rows, "Projection", "Projection", 2, 2026)

        assert result.error is None
        assert len(result.rows) == 1
        r = result.rows[0]
        assert r.raw_financial_type == "Projection as at"
        assert r.item_code == "1"
        assert r.value == 200.0
        assert r.report_month == 2
        assert r.report_year == 2026

    def test_unknown_canonical_name_skipped(self):
        rows = _make_monthly_rows(["Jan"], [[1.0, "T", 0.0]])
        result = parse_monthly_sheet(rows, "Unknown Sheet", "Unknown Sheet", 1, 2026)
        assert result.skipped is True

    def test_no_month_columns_sets_error(self):
        rows = [[None]] * 12 + [[1.0, "Trade", 100.0]]
        rows[11] = [None, None, "NotAMonth"]
        result = parse_monthly_sheet(rows, "Projection", "Projection", 2, 2026)
        assert result.error is not None

    def test_month_year_inference_applied(self):
        # Apr in a Feb 2026 report should map to 2025
        data = [[1.0, "Trade", 500.0]]
        rows = _make_monthly_rows(["Apr"], data)
        result = parse_monthly_sheet(rows, "Projection", "Projection", 2, 2026)
        assert result.rows[0].report_year == 2025
        assert result.rows[0].report_month == 4

    def test_skips_blank_item_code(self):
        data = [[None, "Trade", 100.0]]
        rows = _make_monthly_rows(["Jan"], data)
        result = parse_monthly_sheet(rows, "Cash Flow", "Cash Flow", 1, 2026)
        assert result.rows == []


# ── parse_financial_status extended ──────────────────────────────────────────

class TestParseFinancialStatusExtended:
    def test_zero_value_is_not_none(self):
        """0.0 must be stored as 0.0, not None — it is a meaningful reported value."""
        data = [[1.0, "Trade"] + [None] * 13]
        data[0][2] = 0.0  # Budget Tender = 0.0
        rows = _make_fs_rows(data)
        result = parse_financial_status(rows, 2, 2026)
        budget_rows = [r for r in result.rows if r.raw_financial_type == "Budget Tender"]
        assert budget_rows[0].value == 0.0
        assert budget_rows[0].value is not None

    def test_single_data_row_produces_one_row_per_value_column(self):
        """Each FS_VALUE_COLUMNS entry always generates an ExtractedRow, even if value is None."""
        data = [[1.0, "Trade"] + [None] * 13]
        rows = _make_fs_rows(data)
        result = parse_financial_status(rows, 2, 2026)
        assert len(result.rows) == len(FS_VALUE_COLUMNS)

    def test_filled_columns_have_correct_values_others_none(self):
        """Cols with values return those values; untouched cols return None."""
        data = [[1.0, "Trade"] + [None] * 13]
        data[0][2] = 100.0  # Budget Tender
        data[0][9] = 300.0  # Projection as at
        rows = _make_fs_rows(data)
        result = parse_financial_status(rows, 2, 2026)
        by_ft = {r.raw_financial_type: r.value for r in result.rows}
        assert by_ft["Budget Tender"] == 100.0
        assert by_ft["Projection as at"] == 300.0
        # Every other column should be None
        assert by_ft["Business Plan"] is None
        assert by_ft["Audit Report (WIP)"] is None

    def test_two_data_rows_produce_double_the_rows(self):
        data = [
            [1.0, "Income"] + [None] * 13,
            [2.0, "Cost"]   + [None] * 13,
        ]
        data[0][2] = 500.0
        data[1][2] = 800.0
        rows = _make_fs_rows(data)
        result = parse_financial_status(rows, 2, 2026)
        assert len(result.rows) == len(FS_VALUE_COLUMNS) * 2
        codes = {r.item_code for r in result.rows}
        assert "1" in codes
        assert "2" in codes


# ── parse_monthly_sheet extended ─────────────────────────────────────────────

class TestParseMonthlySheetExtended:
    def test_multiple_month_columns_produce_multiple_rows(self):
        """Three month columns in a single row → three ExtractedRows."""
        data = [[1.0, "Trade", 100.0, 200.0, 300.0]]
        rows = _make_monthly_rows(["Jan", "Feb", "Mar"], data)
        result = parse_monthly_sheet(rows, "Projection", "Projection", 3, 2026)
        assert result.error is None
        assert len(result.rows) == 3
        months = sorted(r.report_month for r in result.rows)
        assert months == [1, 2, 3]

    def test_zero_value_in_monthly_preserved(self):
        data = [[1.0, "Trade", 0.0]]
        rows = _make_monthly_rows(["Feb"], data)
        result = parse_monthly_sheet(rows, "Accrual", "Accrual", 2, 2026)
        assert len(result.rows) == 1
        assert result.rows[0].value == 0.0
        assert result.rows[0].value is not None

    def test_source_cell_ref_correct_for_monthly(self):
        """source_row_number reflects the 1-indexed Excel row of the data row."""
        data = [[1.0, "Trade", 999.0]]
        rows = _make_monthly_rows(["Feb"], data)
        result = parse_monthly_sheet(rows, "Projection", "Projection", 2, 2026)
        r = result.rows[0]
        # data starts at MONTHLY_DATA_START (12, 0-indexed) → Excel row 13
        assert r.source_row_number == 13
        assert r.source_cell_ref.startswith("C")
