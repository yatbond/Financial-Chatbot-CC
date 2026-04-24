"""
Unit tests for the Phase 8 shortcut execution engine.

All tests use InMemoryDataProvider with controlled fixture rows.
No database connection is required.
"""

from __future__ import annotations

import pytest

from src.query_resolver import FieldSet, ResolvedQuery
from src.shortcut_engine import (
    FinancialRow,
    InMemoryDataProvider,
    NoDataResult,
    ShortcutEngine,
    ShortcutHelpResult,
    TableResult,
    TypeListResult,
    ValueResult,
    _months_back,
    _item_code_sort_key,
)

PROJECT = "proj-001"
YEAR = 2026
FS = "Financial Status"
PROJ_SHEET = "Projection"
CF_SHEET = "Cash Flow"
CC_SHEET = "Committed Cost"


# ── Heading map fixture ───────────────────────────────────────────────────────

HEADING_MAP: dict[str, dict] = {
    "1":     {"data_type": "Income",              "friendly_name": "Total Income",              "category": "Income", "tier": 1},
    "1.1":   {"data_type": "Income - OCW",        "friendly_name": "Original Contract Value",   "category": "Income", "tier": 2},
    "1.7":   {"data_type": "Income - Claims",     "friendly_name": "Claims Income",             "category": "Income", "tier": 2},
    "1.2.1": {"data_type": "Income - VO CE",      "friendly_name": "VO / CE Amount",            "category": "Income", "tier": 3},
    "1.8":   {"data_type": "Income - CPF",        "friendly_name": "Price Fluctuation (CPF)",   "category": "Income", "tier": 2},
    "1.12.1":{"data_type": "Income - Other Rev",  "friendly_name": "Other Revenue",             "category": "Income", "tier": 3},
    "2":     {"data_type": "Less : Cost",         "friendly_name": "Total Cost",                "category": "Cost",   "tier": 1},
    "2.1":   {"data_type": "Less : Cost - Prelim","friendly_name": "Preliminaries",             "category": "Cost",   "tier": 2},
    "2.1.1": {"data_type": "Prelim - Mgt",        "friendly_name": "Management & Supervision",  "category": "Cost",   "tier": 3},
    "2.1.2": {"data_type": "Prelim - RE",         "friendly_name": "Resident Engineer Staff",   "category": "Cost",   "tier": 3},
    "2.2":   {"data_type": "Less : Cost - Mat",   "friendly_name": "Total Materials",           "category": "Cost",   "tier": 2},
    "2.2.15":{"data_type": "Mat Savings",         "friendly_name": "Material Savings",          "category": "Cost",   "tier": 3},
    "2.4.4": {"data_type": "Contra Charge",       "friendly_name": "Contra Charge",             "category": "Cost",   "tier": 3},
    "2.4.7": {"data_type": "DSC Savings",         "friendly_name": "Potential Savings (DSC)",   "category": "Cost",   "tier": 3},
    "2.7":   {"data_type": "Contingencies",       "friendly_name": "Allow for Contingencies",   "category": "Cost",   "tier": 2},
    "2.8":   {"data_type": "Rectifications",      "friendly_name": "Allow for Rectifications",  "category": "Cost",   "tier": 2},
    "2.14":  {"data_type": "Stretch Target",      "friendly_name": "Stretch Target (Cost)",     "category": "Cost",   "tier": 2},
    "3":     {"data_type": "Gross Profit",        "friendly_name": "Gross Profit",              "category": "Summary","tier": 1},
    "5":     {"data_type": "GP After Recon",      "friendly_name": "Gross Profit (after recon & overhead)", "category": "Summary", "tier": 1},
}


# ── Row factory ───────────────────────────────────────────────────────────────

def _row(
    item_code: str | None,
    financial_type: str | None,
    value: float,
    sheet: str = FS,
    month: int = 2,
    year: int = YEAR,
    project: str = PROJECT,
) -> FinancialRow:
    meta = HEADING_MAP.get(item_code or "") if item_code else None
    return FinancialRow(
        project_id=project,
        sheet_name=sheet,
        report_month=month,
        report_year=year,
        financial_type=financial_type,
        item_code=item_code,
        data_type=meta["data_type"] if meta else None,
        friendly_name=meta["friendly_name"] if meta else None,
        category=meta["category"] if meta else None,
        tier=meta["tier"] if meta else None,
        value=value,
    )


# ── Resolved query helpers ────────────────────────────────────────────────────

def _resolved(**kwargs) -> ResolvedQuery:
    defaults = dict(
        shortcut=None, shortcut_b=None,
        project_id=PROJECT, project_code="P001", project_name="Test Project",
        sheet_name=None, financial_type=None, data_type=None,
        item_code=None, friendly_name=None, category=None, tier=None,
        month=2, year=YEAR,
        num_months=None, compare_a=None, compare_b=None,
        context_used=[], warnings=[], banner={},
    )
    defaults.update(kwargs)
    return ResolvedQuery(**defaults)


def _fieldset(financial_type=None, data_type=None, item_code=None,
              friendly_name=None, sheet_name=None) -> FieldSet:
    fs = FieldSet()
    fs.financial_type = financial_type
    fs.data_type = data_type
    fs.item_code = item_code
    fs.friendly_name = friendly_name
    fs.sheet_name = sheet_name
    return fs


# ── Helper tests ──────────────────────────────────────────────────────────────

def test_months_back_basic():
    periods = _months_back(3, 2026, 4)
    assert periods == [(12, 2025), (1, 2026), (2, 2026), (3, 2026)]


def test_months_back_year_boundary():
    periods = _months_back(2, 2026, 6)
    assert periods[0] == (9, 2025)
    assert periods[-1] == (2, 2026)
    assert len(periods) == 6


def test_item_code_sort_key():
    codes = ["2.10", "2.2", "1", "2.1"]
    sorted_codes = sorted(codes, key=_item_code_sort_key)
    assert sorted_codes == ["1", "2.1", "2.2", "2.10"]


# ── Direct value retrieval ────────────────────────────────────────────────────

class TestRetrieveValue:
    def setup_method(self):
        self.rows = [
            _row("2.1", "Projection", 500_000, sheet=FS, month=2, year=2026),
        ]
        self.engine = ShortcutEngine(InMemoryDataProvider(self.rows), HEADING_MAP)

    def test_returns_value_result(self):
        r = _resolved(sheet_name=FS, financial_type="Projection", item_code="2.1")
        result = self.engine.execute(r)
        assert isinstance(result, ValueResult)
        assert result.value == 500_000
        assert result.item_code == "2.1"
        assert result.financial_type == "Projection"

    def test_no_data_returns_no_data_result(self):
        r = _resolved(sheet_name=FS, financial_type="Projection", item_code="2.2")
        result = self.engine.execute(r)
        assert isinstance(result, NoDataResult)
        assert "no data" in result.reason.lower()

    def test_missing_project_returns_no_data(self):
        r = _resolved(project_id=None, sheet_name=FS)
        result = self.engine.execute(r)
        assert isinstance(result, NoDataResult)

    def test_period_from_latest_when_not_set(self):
        """If month/year are None, engine should use latest available period."""
        r = _resolved(sheet_name=FS, financial_type="Projection", item_code="2.1",
                      month=None, year=None)
        result = self.engine.execute(r)
        assert isinstance(result, ValueResult)
        assert result.value == 500_000


# ── Shortcut help ─────────────────────────────────────────────────────────────

class TestShortcutHelp:
    def setup_method(self):
        self.engine = ShortcutEngine(InMemoryDataProvider([]), HEADING_MAP)

    def test_returns_shortcut_help_result(self):
        r = _resolved(shortcut="Shortcut")
        result = self.engine.execute(r)
        assert isinstance(result, ShortcutHelpResult)
        names = [item["name"] for item in result.items]
        assert "Analyze" in names
        assert "Compare" in names
        assert "Trend" in names
        assert "Risk" in names
        assert "Cash Flow" in names

    def test_each_item_has_example(self):
        r = _resolved(shortcut="Shortcut")
        result = self.engine.execute(r)
        for item in result.items:
            assert "example" in item
            assert item["example"]


# ── Type list ─────────────────────────────────────────────────────────────────

class TestTypeList:
    def setup_method(self):
        self.engine = ShortcutEngine(InMemoryDataProvider([]), HEADING_MAP)

    def test_returns_type_list_result(self):
        r = _resolved(shortcut="Type")
        result = self.engine.execute(r)
        assert isinstance(result, TypeListResult)
        ft_names = [item["financial_type"] for item in result.items]
        assert "Projection" in ft_names
        assert "WIP" in ft_names
        assert "Cash Flow" in ft_names
        assert "Business Plan" in ft_names

    def test_items_have_sheet_name(self):
        r = _resolved(shortcut="Type")
        result = self.engine.execute(r)
        for item in result.items:
            assert "sheet_name" in item
            assert item["sheet_name"]


# ── List ──────────────────────────────────────────────────────────────────────

class TestList:
    def setup_method(self):
        self.engine = ShortcutEngine(InMemoryDataProvider([]), HEADING_MAP)

    def test_list_all_returns_tier_1_and_2(self):
        r = _resolved(shortcut="List")
        result = self.engine.execute(r)
        assert isinstance(result, TableResult)
        tiers = {row["Tier"] for row in result.rows}
        assert tiers == {1, 2}

    def test_list_all_does_not_include_tier_3(self):
        r = _resolved(shortcut="List")
        result = self.engine.execute(r)
        assert all(row["Tier"] <= 2 for row in result.rows)

    def test_list_by_item_code_returns_subtree(self):
        r = _resolved(shortcut="List", item_code="2.1")
        result = self.engine.execute(r)
        assert isinstance(result, TableResult)
        codes = {row["Item Code"] for row in result.rows}
        assert "2.1" in codes
        assert "2.1.1" in codes
        assert "2.1.2" in codes
        assert "2.2" not in codes

    def test_list_by_unknown_code_returns_no_data(self):
        r = _resolved(shortcut="List", item_code="9.9")
        result = self.engine.execute(r)
        assert isinstance(result, NoDataResult)

    def test_list_rows_sorted_by_item_code(self):
        r = _resolved(shortcut="List", item_code="2.1")
        result = self.engine.execute(r)
        codes = [row["Item Code"] for row in result.rows]
        assert codes == sorted(codes, key=_item_code_sort_key)


# ── Total ─────────────────────────────────────────────────────────────────────

class TestTotal:
    def setup_method(self):
        self.rows = [
            _row("2.1",   "Projection", 900_000),
            _row("2.1.1", "Projection", 400_000),
            _row("2.1.2", "Projection", 500_000),
        ]
        self.engine = ShortcutEngine(InMemoryDataProvider(self.rows), HEADING_MAP)

    def test_returns_table_result(self):
        r = _resolved(shortcut="Total", sheet_name=FS, financial_type="Projection",
                      item_code="2.1", friendly_name="Preliminaries")
        result = self.engine.execute(r)
        assert isinstance(result, TableResult)
        assert result.shortcut == "Total"

    def test_shows_immediate_children_only(self):
        r = _resolved(shortcut="Total", sheet_name=FS, financial_type="Projection",
                      item_code="2.1", friendly_name="Preliminaries")
        result = self.engine.execute(r)
        codes = [row["Item Code"] for row in result.rows]
        assert "2.1.1" in codes
        assert "2.1.2" in codes
        assert "2.1" not in codes  # parent is in footer, not rows

    def test_footer_has_total(self):
        r = _resolved(shortcut="Total", sheet_name=FS, financial_type="Projection",
                      item_code="2.1", friendly_name="Preliminaries")
        result = self.engine.execute(r)
        assert result.footer is not None
        assert result.footer["Value"] == 900_000

    def test_no_data_returns_no_data_result(self):
        r = _resolved(shortcut="Total", sheet_name=FS, financial_type="Projection",
                      item_code="9.9")
        result = self.engine.execute(r)
        assert isinstance(result, NoDataResult)

    def test_missing_item_code_returns_no_data(self):
        r = _resolved(shortcut="Total", sheet_name=FS, financial_type="Projection")
        result = self.engine.execute(r)
        assert isinstance(result, NoDataResult)


# ── Detail ────────────────────────────────────────────────────────────────────

class TestDetail:
    def setup_method(self):
        # 2-level hierarchy under 2.1
        self.rows = [
            _row("2.1",   "Cash Flow", 900_000),
            _row("2.1.1", "Cash Flow", 400_000),
            _row("2.1.2", "Cash Flow", 500_000),
        ]
        self.engine = ShortcutEngine(InMemoryDataProvider(self.rows), HEADING_MAP)

    def test_returns_table_result_with_children(self):
        r = _resolved(shortcut="Detail", sheet_name=FS, financial_type="Cash Flow",
                      item_code="2.1", friendly_name="Preliminaries")
        result = self.engine.execute(r)
        assert isinstance(result, TableResult)
        assert result.shortcut == "Detail"

    def test_excludes_parent_row(self):
        r = _resolved(shortcut="Detail", sheet_name=FS, financial_type="Cash Flow",
                      item_code="2.1", friendly_name="Preliminaries")
        result = self.engine.execute(r)
        codes = [row["Item Code"] for row in result.rows]
        assert "2.1" not in codes
        assert "2.1.1" in codes
        assert "2.1.2" in codes

    def test_no_children_returns_no_data(self):
        # Only parent row, no children
        rows = [_row("2.1", "Cash Flow", 900_000)]
        engine = ShortcutEngine(InMemoryDataProvider(rows), HEADING_MAP)
        r = _resolved(shortcut="Detail", sheet_name=FS, financial_type="Cash Flow",
                      item_code="2.1")
        result = engine.execute(r)
        assert isinstance(result, NoDataResult)


# ── Analyze ───────────────────────────────────────────────────────────────────

class TestAnalyze:
    def _make_engine(self, rows):
        return ShortcutEngine(InMemoryDataProvider(rows), HEADING_MAP)

    def test_returns_table_result(self):
        rows = [
            # Projection income item lower than WIP → exception (proj_less_b)
            _row("1.1", "Projection", 800_000),
            _row("1.1", "WIP",        900_000),
            # OK income item (proj >= wip)
            _row("1.7", "Projection", 200_000),
            _row("1.7", "WIP",        150_000),
        ]
        engine = self._make_engine(rows)
        r = _resolved(shortcut="Analyze", sheet_name=FS)
        result = engine.execute(r)
        assert isinstance(result, TableResult)
        assert result.shortcut == "Analyze"

    def test_income_exception_proj_less_wip(self):
        rows = [
            _row("1.1", "Projection", 800_000),
            _row("1.1", "WIP",        900_000),
        ]
        result = self._make_engine(rows).execute(_resolved(shortcut="Analyze"))
        assert isinstance(result, TableResult)
        assert len(result.rows) == 1
        assert result.rows[0]["Item Code"] == "1.1"
        assert result.rows[0]["Rule"] == "Projection vs WIP"

    def test_cost_exception_proj_greater_accrual(self):
        rows = [
            _row("2.1", "Projection", 500_000),
            _row("2.1", "Accrual",    400_000),
        ]
        result = self._make_engine(rows).execute(_resolved(shortcut="Analyze"))
        assert isinstance(result, TableResult)
        exceptions = [row for row in result.rows if row["Rule"] == "Projection vs Accrual"]
        assert len(exceptions) == 1
        assert exceptions[0]["Difference"] == pytest.approx(100_000)

    def test_no_exceptions_returns_empty_table(self):
        rows = [
            # Income OK: proj >= wip
            _row("1.1", "Projection", 1_000_000),
            _row("1.1", "WIP",          900_000),
            # Cost OK: proj <= accrual
            _row("2.1", "Projection", 400_000),
            _row("2.1", "Accrual",    500_000),
        ]
        result = self._make_engine(rows).execute(_resolved(shortcut="Analyze"))
        assert isinstance(result, TableResult)
        assert result.rows == []
        assert "no exceptions" in result.title.lower()

    def test_no_data_returns_no_data_result(self):
        # No data AND no month/year on resolved → get_latest_period returns None
        engine = ShortcutEngine(InMemoryDataProvider([]), HEADING_MAP)
        r = _resolved(shortcut="Analyze", project_id="ghost-project", month=None, year=None)
        result = engine.execute(r)
        assert isinstance(result, NoDataResult)

    def test_tier_3_items_excluded(self):
        # tier-3 items should not appear in Analyze (only tier 1+2)
        rows = [
            _row("1.2.1", "Projection", 100),  # tier 3 income
            _row("1.2.1", "WIP",        200),
        ]
        result = self._make_engine(rows).execute(_resolved(shortcut="Analyze"))
        assert isinstance(result, TableResult)
        assert result.rows == []


# ── Compare ───────────────────────────────────────────────────────────────────

class TestCompare:
    def _make_engine(self, rows):
        return ShortcutEngine(InMemoryDataProvider(rows), HEADING_MAP)

    def test_returns_table_result(self):
        rows = [
            _row("1.1", "Projection", 800_000),
            _row("1.1", "WIP",        900_000),
        ]
        engine = self._make_engine(rows)
        r = _resolved(
            shortcut="Compare", sheet_name=FS,
            compare_a=_fieldset("Projection", item_code="1.1",
                                friendly_name="Original Contract Value",
                                sheet_name=FS),
            compare_b=_fieldset("WIP", item_code="1.1",
                                friendly_name="Original Contract Value",
                                sheet_name=FS),
        )
        result = engine.execute(r)
        assert isinstance(result, TableResult)
        assert result.shortcut == "Compare"

    def test_difference_is_correct(self):
        rows = [
            _row("1.1", "Projection", 800_000),
            _row("1.1", "WIP",        900_000),
        ]
        engine = self._make_engine(rows)
        r = _resolved(
            shortcut="Compare", sheet_name=FS,
            compare_a=_fieldset("Projection", item_code="1.1", sheet_name=FS),
            compare_b=_fieldset("WIP",        item_code="1.1", sheet_name=FS),
        )
        result = engine.execute(r)
        assert isinstance(result, TableResult)
        row = result.rows[0]
        diff_col = "Difference"
        assert row[diff_col] == pytest.approx(-100_000)

    def test_missing_one_side_returns_table_with_warning(self):
        rows = [_row("1.1", "Projection", 800_000)]
        engine = self._make_engine(rows)
        r = _resolved(
            shortcut="Compare", sheet_name=FS,
            compare_a=_fieldset("Projection", item_code="1.1", sheet_name=FS),
            compare_b=_fieldset("WIP",        item_code="1.1", sheet_name=FS),
        )
        result = engine.execute(r)
        assert isinstance(result, TableResult)
        assert any("no data" in w.lower() for w in result.warnings)

    def test_both_sides_missing_returns_no_data(self):
        engine = self._make_engine([])
        r = _resolved(
            shortcut="Compare", sheet_name=FS,
            compare_a=_fieldset("Projection", item_code="1.1", sheet_name=FS),
            compare_b=_fieldset("WIP",        item_code="1.1", sheet_name=FS),
        )
        result = engine.execute(r)
        assert isinstance(result, NoDataResult)

    def test_missing_compare_sides_returns_no_data(self):
        r = _resolved(shortcut="Compare", sheet_name=FS)
        result = self._make_engine([]).execute(r)
        assert isinstance(result, NoDataResult)


# ── Trend ─────────────────────────────────────────────────────────────────────

class TestTrend:
    def _make_rows(self, periods: list[tuple[int, int]]) -> list[FinancialRow]:
        return [
            _row("2.1", "Projection", float(i * 100_000), sheet=PROJ_SHEET, month=m, year=y)
            for i, (m, y) in enumerate(periods, start=1)
        ]

    def test_returns_table_result(self):
        periods = [(9, 2025), (10, 2025), (11, 2025), (12, 2025), (1, 2026), (2, 2026)]
        engine = ShortcutEngine(InMemoryDataProvider(self._make_rows(periods)), HEADING_MAP)
        r = _resolved(
            shortcut="Trend", sheet_name=PROJ_SHEET,
            financial_type="Projection", item_code="2.1",
            friendly_name="Preliminaries",
            month=2, year=2026, num_months=6,
        )
        result = engine.execute(r)
        assert isinstance(result, TableResult)
        assert result.shortcut == "Trend"
        assert len(result.rows) == 6

    def test_rows_in_chronological_order(self):
        periods = [(12, 2025), (1, 2026), (2, 2026)]
        engine = ShortcutEngine(InMemoryDataProvider(self._make_rows(periods)), HEADING_MAP)
        r = _resolved(
            shortcut="Trend", sheet_name=PROJ_SHEET,
            financial_type="Projection", item_code="2.1",
            month=2, year=2026, num_months=3,
        )
        result = engine.execute(r)
        assert isinstance(result, TableResult)
        assert result.rows[0]["Period"] == "Dec 2025"
        assert result.rows[-1]["Period"] == "Feb 2026"

    def test_none_value_for_missing_months(self):
        # Only 2 out of 6 months have data
        periods = [(1, 2026), (2, 2026)]
        engine = ShortcutEngine(InMemoryDataProvider(self._make_rows(periods)), HEADING_MAP)
        r = _resolved(
            shortcut="Trend", sheet_name=PROJ_SHEET,
            financial_type="Projection", item_code="2.1",
            month=2, year=2026, num_months=6,
        )
        result = engine.execute(r)
        assert isinstance(result, TableResult)
        assert len(result.rows) == 6
        none_count = sum(1 for row in result.rows if row["Value"] is None)
        assert none_count == 4

    def test_no_data_returns_no_data_result(self):
        engine = ShortcutEngine(InMemoryDataProvider([]), HEADING_MAP)
        r = _resolved(
            shortcut="Trend", sheet_name=PROJ_SHEET,
            financial_type="Projection", item_code="2.1",
            month=2, year=2026,
        )
        result = engine.execute(r)
        assert isinstance(result, NoDataResult)

    def test_uses_latest_period_when_month_year_absent(self):
        periods = [(1, 2026), (2, 2026), (3, 2026)]
        engine = ShortcutEngine(InMemoryDataProvider(self._make_rows(periods)), HEADING_MAP)
        r = _resolved(
            shortcut="Trend", sheet_name=PROJ_SHEET,
            financial_type="Projection", item_code="2.1",
            month=None, year=None, num_months=3,
        )
        result = engine.execute(r)
        assert isinstance(result, TableResult)
        assert result.rows[-1]["Period"] == "Mar 2026"


# ── Trend Compare ─────────────────────────────────────────────────────────────

class TestTrendCompare:
    def _make_rows(self) -> list[FinancialRow]:
        rows = []
        for i, (m, y) in enumerate([(12, 2025), (1, 2026), (2, 2026)], start=1):
            rows.append(_row("1.1", "Projection", float(i * 100_000), sheet=FS, month=m, year=y))
            rows.append(_row("1.1", "WIP",        float(i * 90_000),  sheet=FS, month=m, year=y))
        return rows

    def test_returns_table_result_with_diff_column(self):
        engine = ShortcutEngine(InMemoryDataProvider(self._make_rows()), HEADING_MAP)
        r = _resolved(
            shortcut="Trend", shortcut_b="Compare", sheet_name=FS,
            month=2, year=2026, num_months=3,
            compare_a=_fieldset("Projection", item_code="1.1",
                                friendly_name="Original Contract Value", sheet_name=FS),
            compare_b=_fieldset("WIP",        item_code="1.1",
                                friendly_name="Original Contract Value", sheet_name=FS),
        )
        result = engine.execute(r)
        assert isinstance(result, TableResult)
        assert "Difference" in result.columns
        assert len(result.rows) == 3

    def test_difference_values_correct(self):
        engine = ShortcutEngine(InMemoryDataProvider(self._make_rows()), HEADING_MAP)
        r = _resolved(
            shortcut="Trend", shortcut_b="Compare", sheet_name=FS,
            month=2, year=2026, num_months=3,
            compare_a=_fieldset("Projection", item_code="1.1", sheet_name=FS),
            compare_b=_fieldset("WIP",        item_code="1.1", sheet_name=FS),
        )
        result = engine.execute(r)
        # Month 1 (Dec 2025): proj=100k, wip=90k → diff=10k
        diff_col = [c for c in result.columns if c == "Difference"][0]
        assert result.rows[0][diff_col] == pytest.approx(10_000)

    def test_no_data_returns_no_data_result(self):
        engine = ShortcutEngine(InMemoryDataProvider([]), HEADING_MAP)
        r = _resolved(
            shortcut="Trend", shortcut_b="Compare",
            compare_a=_fieldset("Projection", item_code="1.1", sheet_name=FS),
            compare_b=_fieldset("WIP",        item_code="1.1", sheet_name=FS),
        )
        result = engine.execute(r)
        assert isinstance(result, NoDataResult)


# ── Total Compare ─────────────────────────────────────────────────────────────

class TestTotalCompare:
    def _make_rows(self) -> list[FinancialRow]:
        return [
            _row("2.1.1", "Projection",    400_000),
            _row("2.1.2", "Projection",    500_000),
            _row("2.1.1", "Business Plan", 350_000),
            _row("2.1.2", "Business Plan", 450_000),
        ]

    def test_returns_table_result(self):
        engine = ShortcutEngine(InMemoryDataProvider(self._make_rows()), HEADING_MAP)
        r = _resolved(
            shortcut="Total", shortcut_b="Compare", sheet_name=FS,
            compare_a=_fieldset("Projection",    item_code="2.1",
                                friendly_name="Preliminaries", sheet_name=FS),
            compare_b=_fieldset("Business Plan", item_code="2.1",
                                friendly_name="Preliminaries", sheet_name=FS),
        )
        result = engine.execute(r)
        assert isinstance(result, TableResult)
        assert result.shortcut == "Total"
        assert result.footer is not None

    def test_footer_totals_are_correct(self):
        engine = ShortcutEngine(InMemoryDataProvider(self._make_rows()), HEADING_MAP)
        r = _resolved(
            shortcut="Total", shortcut_b="Compare", sheet_name=FS,
            compare_a=_fieldset("Projection",    item_code="2.1", sheet_name=FS),
            compare_b=_fieldset("Business Plan", item_code="2.1", sheet_name=FS),
        )
        result = engine.execute(r)
        footer = result.footer
        # Projection total = 400k + 500k = 900k
        # BP total = 350k + 450k = 800k
        proj_col = [c for c in result.columns if "Projection" in c][0]
        bp_col   = [c for c in result.columns if "Business Plan" in c][0]
        assert footer[proj_col] == pytest.approx(900_000)
        assert footer[bp_col]   == pytest.approx(800_000)
        assert footer["Difference"] == pytest.approx(100_000)

    def test_no_data_returns_no_data_result(self):
        engine = ShortcutEngine(InMemoryDataProvider([]), HEADING_MAP)
        r = _resolved(
            shortcut="Total", shortcut_b="Compare",
            compare_a=_fieldset("Projection",    item_code="2.1", sheet_name=FS),
            compare_b=_fieldset("Business Plan", item_code="2.1", sheet_name=FS),
        )
        result = engine.execute(r)
        assert isinstance(result, NoDataResult)


# ── Risk ──────────────────────────────────────────────────────────────────────

class TestRisk:
    def _make_risk_rows(self) -> list[FinancialRow]:
        rows = []
        risk_codes = [
            ("1.2.1", "Income"),
            ("1.7",   "Income"),
            ("2.7",   "Cost"),
            ("2.8",   "Cost"),
            ("2.14",  "Cost"),
        ]
        for code, _ in risk_codes:
            rows.append(_row(code, "WIP",            float(hash(code + "wip") % 1_000_000 + 100_000)))
            rows.append(_row(code, "Committed Cost", float(hash(code + "cc")  % 1_000_000 + 100_000)))
            rows.append(_row(code, "Cash Flow",      float(hash(code + "cf")  % 1_000_000 + 100_000)))
        return rows

    def test_returns_table_result(self):
        engine = ShortcutEngine(InMemoryDataProvider(self._make_risk_rows()), HEADING_MAP)
        r = _resolved(shortcut="Risk", sheet_name=FS)
        result = engine.execute(r)
        assert isinstance(result, TableResult)
        assert result.shortcut == "Risk"

    def test_columns_include_all_three_ft(self):
        engine = ShortcutEngine(InMemoryDataProvider(self._make_risk_rows()), HEADING_MAP)
        r = _resolved(shortcut="Risk", sheet_name=FS)
        result = engine.execute(r)
        assert "WIP" in result.columns
        assert "Committed Cost" in result.columns
        assert "Cash Flow" in result.columns

    def test_only_coded_risk_items_appear(self):
        engine = ShortcutEngine(InMemoryDataProvider(self._make_risk_rows()), HEADING_MAP)
        r = _resolved(shortcut="Risk", sheet_name=FS)
        result = engine.execute(r)
        result_codes = {row["Item Code"] for row in result.rows}
        # Should not include 2.1 (not a risk code)
        assert "2.1" not in result_codes

    def test_no_data_returns_no_data_result(self):
        engine = ShortcutEngine(InMemoryDataProvider([]), HEADING_MAP)
        r = _resolved(shortcut="Risk", project_id="ghost")
        result = engine.execute(r)
        assert isinstance(result, NoDataResult)


# ── Cash Flow Shortcut ────────────────────────────────────────────────────────

class TestCashFlowShortcut:
    def _make_rows(self) -> list[FinancialRow]:
        rows = []
        for i, (m, y) in enumerate([(3, 2025), (6, 2025), (9, 2025), (12, 2025),
                                     (1, 2026), (2, 2026)], start=1):
            rows.append(_row("3", None, float(i * 50_000),  sheet=CF_SHEET, month=m, year=y))
            rows.append(_row("5", None, float(i * 40_000),  sheet=CF_SHEET, month=m, year=y))
        return rows

    def test_returns_table_result(self):
        engine = ShortcutEngine(InMemoryDataProvider(self._make_rows()), HEADING_MAP)
        r = _resolved(shortcut="Cash Flow Shortcut")
        result = engine.execute(r)
        assert isinstance(result, TableResult)
        assert result.shortcut == "Cash Flow Shortcut"

    def test_columns_include_both_items(self):
        engine = ShortcutEngine(InMemoryDataProvider(self._make_rows()), HEADING_MAP)
        r = _resolved(shortcut="Cash Flow Shortcut")
        result = engine.execute(r)
        assert "Gross Profit" in result.columns
        assert "Gross Profit (after recon & overhead)" in result.columns

    def test_up_to_12_months_shown(self):
        engine = ShortcutEngine(InMemoryDataProvider(self._make_rows()), HEADING_MAP)
        r = _resolved(shortcut="Cash Flow Shortcut")
        result = engine.execute(r)
        # Only 6 months of fixture data, so should have at most 6 rows
        assert len(result.rows) <= 12

    def test_only_rows_with_data_included(self):
        engine = ShortcutEngine(InMemoryDataProvider(self._make_rows()), HEADING_MAP)
        r = _resolved(shortcut="Cash Flow Shortcut")
        result = engine.execute(r)
        for row in result.rows:
            assert row.get("Gross Profit") is not None or row.get("Gross Profit (after recon & overhead)") is not None

    def test_no_cf_data_returns_no_data(self):
        engine = ShortcutEngine(InMemoryDataProvider([]), HEADING_MAP)
        r = _resolved(shortcut="Cash Flow Shortcut")
        result = engine.execute(r)
        assert isinstance(result, NoDataResult)


# ── InMemoryDataProvider contract tests ──────────────────────────────────────

class TestInMemoryDataProvider:
    def setup_method(self):
        self.rows = [
            _row("2.1",   "Projection", 500_000, month=2, year=2026),
            _row("2.1",   "Projection", 490_000, month=1, year=2026),
            _row("2.1",   "WIP",        510_000, month=2, year=2026),
            _row("2.1.1", "Projection", 200_000, month=2, year=2026),
        ]
        self.provider = InMemoryDataProvider(self.rows)

    def test_filter_by_financial_type(self):
        rows = self.provider.fetch_rows(PROJECT, FS, financial_type="WIP")
        assert all(r.financial_type == "WIP" for r in rows)
        assert len(rows) == 1

    def test_filter_by_item_code(self):
        rows = self.provider.fetch_rows(PROJECT, FS, item_code="2.1")
        assert all(r.item_code == "2.1" for r in rows)

    def test_item_code_prefix_includes_children(self):
        rows = self.provider.fetch_rows(PROJECT, FS, item_code_prefix="2.1")
        codes = {r.item_code for r in rows}
        assert "2.1" in codes
        assert "2.1.1" in codes

    def test_item_code_prefix_excludes_non_children(self):
        rows = self.provider.fetch_rows(PROJECT, FS, item_code_prefix="2.1")
        # "2" should not be included (it's an ancestor, not a child of 2.1)
        assert all(r.item_code is not None and
                   (r.item_code == "2.1" or r.item_code.startswith("2.1."))
                   for r in rows)

    def test_fetch_rows_for_periods(self):
        rows = self.provider.fetch_rows_for_periods(
            PROJECT, FS, "Projection", "2.1", [(2, 2026), (1, 2026)]
        )
        assert len(rows) == 2

    def test_get_latest_period(self):
        period = self.provider.get_latest_period(PROJECT, FS)
        assert period == (2, 2026)

    def test_get_latest_period_no_data(self):
        period = self.provider.get_latest_period("unknown", FS)
        assert period is None

    def test_get_latest_period_with_ft_filter(self):
        period = self.provider.get_latest_period(PROJECT, FS, financial_type="WIP")
        assert period == (2, 2026)


# ── Additional retrieve value edge cases ──────────────────────────────────────

class TestRetrieveValueEdgeCases:
    def test_missing_sheet_name_returns_no_data(self):
        """sheet_name=None must return NoDataResult, never raise."""
        engine = ShortcutEngine(InMemoryDataProvider([]), HEADING_MAP)
        r = _resolved(shortcut=None, sheet_name=None, item_code="2.1")
        result = engine.execute(r)
        assert isinstance(result, NoDataResult)
        assert "missing" in result.reason.lower() or "sheet" in result.reason.lower()

    def test_project_id_none_returns_no_data(self):
        engine = ShortcutEngine(InMemoryDataProvider([]), HEADING_MAP)
        r = _resolved(shortcut=None, project_id=None, sheet_name=FS)
        result = engine.execute(r)
        assert isinstance(result, NoDataResult)


# ── Analyze multi-rule ────────────────────────────────────────────────────────

class TestAnalyzeMultiRule:
    def test_income_and_cost_exceptions_both_returned(self):
        """Both income exceptions (proj < wip) and cost exceptions (proj > accrual)
        should appear in the same result when both conditions hold."""
        rows = [
            _row("1.1", "Projection", 800_000),
            _row("1.1", "WIP",        900_000),
            _row("2.1", "Projection", 600_000),
            _row("2.1", "Accrual",    400_000),
        ]
        engine = ShortcutEngine(InMemoryDataProvider(rows), HEADING_MAP)
        r = _resolved(shortcut="Analyze", sheet_name=FS)
        result = engine.execute(r)
        assert isinstance(result, TableResult)
        rules = {row["Rule"] for row in result.rows}
        assert "Projection vs WIP" in rules
        assert "Projection vs Accrual" in rules
        assert len(result.rows) >= 2

    def test_analyze_difference_column_correct_sign(self):
        """Difference = Projection - Comparison (can be negative for income exceptions)."""
        rows = [
            _row("1.1", "Projection", 700_000),
            _row("1.1", "WIP",        900_000),
        ]
        engine = ShortcutEngine(InMemoryDataProvider(rows), HEADING_MAP)
        r = _resolved(shortcut="Analyze", sheet_name=FS)
        result = engine.execute(r)
        assert isinstance(result, TableResult)
        diff = result.rows[0]["Difference"]
        assert diff == pytest.approx(-200_000)


# ── Cash flow — full 12 months ────────────────────────────────────────────────

class TestCashFlowFull12Months:
    def _make_12_month_rows(self) -> list[FinancialRow]:
        periods = _months_back(2, 2026, 12)
        rows = []
        for m, y in periods:
            rows.append(_row("3", None, 100_000.0, sheet=CF_SHEET, month=m, year=y))
            rows.append(_row("5", None, 80_000.0,  sheet=CF_SHEET, month=m, year=y))
        return rows

    def test_returns_exactly_12_rows(self):
        engine = ShortcutEngine(InMemoryDataProvider(self._make_12_month_rows()), HEADING_MAP)
        r = _resolved(shortcut="Cash Flow Shortcut")
        result = engine.execute(r)
        assert isinstance(result, TableResult)
        assert len(result.rows) == 12

    def test_rows_in_chronological_order(self):
        engine = ShortcutEngine(InMemoryDataProvider(self._make_12_month_rows()), HEADING_MAP)
        r = _resolved(shortcut="Cash Flow Shortcut")
        result = engine.execute(r)
        periods = [row["Period"] for row in result.rows]
        assert periods[-1] == "Feb 2026"
        assert periods[0] == "Mar 2025"
