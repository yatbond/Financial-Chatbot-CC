"""
Integration tests for resolver_service.py.
All tests use InMemoryDataProvider and QueryResolver.from_csv_strings — no DB required.
"""

from __future__ import annotations

import pytest

from src.query_resolver import AmbiguityResult, QueryResolver, ResolvedQuery
from src.shortcut_engine import (
    FinancialRow,
    InMemoryDataProvider,
    NoDataResult,
    ShortcutHelpResult,
    TableResult,
    TypeListResult,
    ValueResult,
    _FINANCIAL_TYPE_REFS,
    _SHORTCUT_DESCRIPTIONS,
)
from src.resolver_service import (
    _ambiguity_to_response,
    _exec_to_response,
    resolve_and_execute,
)

# ── Minimal fixtures (same style as test_query_resolver.py) ──────────────────

FINANCIAL_TYPE_CSV = """\
Raw_Financial_Type,Clean_Financial_Type,Acronyms
Budget Revision as at,Latest Budget,latest budget|budget|revision|rev
Business Plan,Business Plan,bp|business plan
Audit Report (WIP),WIP,wip|audit
Projection as at,Projection,projected|projection
Committed Value / Cost as at,Committed Cost,committed|committed cost
Cash Flow Actual received & paid as at,Cash Flow,cf|cashflow|cash flow|cash
Budget Tender,Budget Tender,tender
"""

HEADING_CSV = """\
Item_Code,Data_Type,Friendly_Name,Category,Tier,Acronyms
1,Income,Total Income,Income,1,income|revenue|total income
1.1,Income - OCW,Original Contract Value,Income,2,ocw|original contract
2,Less : Cost,Total Cost,Cost,1,cost|total cost
2.1,Less : Cost - Preliminaries,Preliminaries,Cost,2,prelim|preliminaries
3,Gross Profit (Item 1.0-2.0),Gross Profit,Summary,1,gp|gross profit|profit
5,Gross Profit (after recon),GP after Recon,Summary,1,gp after recon|net gp
"""

PROJECT = "proj-001"
FS = "Financial Status"

HEADING_MAP = {
    "1":   {"data_type": "Income",                      "friendly_name": "Total Income",    "category": "Income",  "tier": 1},
    "1.1": {"data_type": "Income - OCW",                "friendly_name": "Original Contract Value", "category": "Income", "tier": 2},
    "2":   {"data_type": "Less : Cost",                 "friendly_name": "Total Cost",      "category": "Cost",    "tier": 1},
    "2.1": {"data_type": "Less : Cost - Preliminaries", "friendly_name": "Preliminaries",   "category": "Cost",    "tier": 2},
    "3":   {"data_type": "Gross Profit (Item 1.0-2.0)", "friendly_name": "Gross Profit",    "category": "Summary", "tier": 1},
    "5":   {"data_type": "Gross Profit (after recon)",  "friendly_name": "GP after Recon",  "category": "Summary", "tier": 1},
}


@pytest.fixture(scope="module")
def resolver() -> QueryResolver:
    return QueryResolver.from_csv_strings(FINANCIAL_TYPE_CSV, HEADING_CSV)


def _make_row(
    item_code: str,
    financial_type: str | None,
    value: float,
    sheet: str = FS,
    month: int = 2,
    year: int = 2026,
) -> FinancialRow:
    meta = HEADING_MAP.get(item_code or "")
    return FinancialRow(
        project_id=PROJECT,
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


# ── _exec_to_response: ValueResult ───────────────────────────────────────────

class TestExecToResponseValue:
    def test_type_is_result(self):
        resolved = ResolvedQuery(
            financial_type="Projection", data_type="Gross Profit",
            sheet_name=FS, month=2, year=2026,
        )
        exec_result = ValueResult(
            label="Gross Profit", value=12_450_000,
            period="Feb 2026", financial_type="Projection",
            data_type="Gross Profit", item_code="3",
        )
        resp = _exec_to_response(resolved, exec_result)
        assert resp["type"] == "result"

    def test_value_in_row(self):
        resolved = ResolvedQuery(financial_type="Projection", sheet_name=FS)
        exec_result = ValueResult(
            label="GP", value=5_000_000, period="Feb 2026",
            financial_type="Projection", data_type="Gross Profit", item_code="3",
        )
        resp = _exec_to_response(resolved, exec_result)
        assert resp["rows"][0]["Value (HK$)"] == 5_000_000

    def test_interpretation_fields_present(self):
        resolved = ResolvedQuery(
            financial_type="Projection", data_type="Gross Profit",
            sheet_name=FS, month=2, year=2026,
        )
        exec_result = ValueResult(
            label="GP", value=0, period="Feb 2026",
            financial_type="Projection", data_type="Gross Profit", item_code="3",
        )
        resp = _exec_to_response(resolved, exec_result)
        assert "financial_type" in resp["interpretation"]
        assert "data_type" in resp["interpretation"]
        assert "sheet_name" in resp["interpretation"]
        assert "period" in resp["interpretation"]

    def test_context_update_present(self):
        resolved = ResolvedQuery(financial_type="WIP", sheet_name=FS)
        exec_result = ValueResult(
            label="GP", value=1, period="Feb 2026",
            financial_type="WIP", data_type="Gross Profit", item_code="3",
        )
        resp = _exec_to_response(resolved, exec_result)
        assert "context_update" in resp
        assert resp["context_update"]["sheet_name"] == FS

    def test_warning_included_when_present(self):
        resolved = ResolvedQuery(financial_type="WIP", sheet_name=FS, warnings=["Watch out"])
        exec_result = ValueResult(
            label="GP", value=1, period="Feb 2026",
            financial_type="WIP", data_type="Gross Profit", item_code="3",
            warnings=["Watch out"],
        )
        resp = _exec_to_response(resolved, exec_result)
        assert resp["warning"] == "Watch out"

    def test_no_warning_when_empty(self):
        resolved = ResolvedQuery(financial_type="Projection", sheet_name=FS)
        exec_result = ValueResult(
            label="GP", value=1, period="Feb 2026",
            financial_type="Projection", data_type="Gross Profit", item_code="3",
        )
        resp = _exec_to_response(resolved, exec_result)
        assert resp["warning"] is None


# ── _exec_to_response: TableResult ───────────────────────────────────────────

class TestExecToResponseTable:
    def test_type_is_result(self):
        resolved = ResolvedQuery(shortcut="Trend", financial_type="Projection", sheet_name="Projection")
        exec_result = TableResult(
            shortcut="Trend", title="Trend: Gross Profit",
            columns=["Period", "GP"], rows=[{"Period": "Feb 2026", "GP": 1_000_000}],
        )
        resp = _exec_to_response(resolved, exec_result)
        assert resp["type"] == "result"

    def test_columns_and_rows_pass_through(self):
        resolved = ResolvedQuery(shortcut="List", sheet_name=FS)
        exec_result = TableResult(
            shortcut="List", columns=["Code", "Name"],
            rows=[{"Code": "1", "Name": "Income"}],
        )
        resp = _exec_to_response(resolved, exec_result)
        assert resp["columns"] == ["Code", "Name"]
        assert resp["rows"][0]["Code"] == "1"

    def test_shortcut_in_interpretation(self):
        resolved = ResolvedQuery(shortcut="Analyze", sheet_name=FS)
        exec_result = TableResult(shortcut="Analyze", columns=["Rule"], rows=[])
        resp = _exec_to_response(resolved, exec_result)
        assert resp["interpretation"]["shortcut"] == "Analyze"


# ── _exec_to_response: NoDataResult ──────────────────────────────────────────

class TestExecToResponseNoData:
    def test_type_is_missing(self):
        resolved = ResolvedQuery(financial_type="WIP", sheet_name=FS)
        resp = _exec_to_response(resolved, NoDataResult(reason="No rows."))
        assert resp["type"] == "missing"

    def test_message_from_reason(self):
        resolved = ResolvedQuery(financial_type="WIP", sheet_name=FS)
        resp = _exec_to_response(resolved, NoDataResult(reason="No rows found for item 3."))
        assert "No rows found" in resp["message"]


# ── _exec_to_response: ShortcutHelpResult / TypeListResult ───────────────────

class TestExecToResponseInfo:
    def test_shortcut_help_type_is_info(self):
        resolved = ResolvedQuery(shortcut="Shortcut")
        resp = _exec_to_response(resolved, ShortcutHelpResult(items=_SHORTCUT_DESCRIPTIONS[:2]))
        assert resp["type"] == "info"
        assert resp["title"] == "Supported Shortcuts"
        assert len(resp["content"]) > 0

    def test_type_list_type_is_info(self):
        resolved = ResolvedQuery(shortcut="Type")
        resp = _exec_to_response(resolved, TypeListResult(items=_FINANCIAL_TYPE_REFS[:3]))
        assert resp["type"] == "info"
        assert resp["title"] == "Available Financial Types & Sheets"
        assert "Projection" in resp["content"]


# ── _ambiguity_to_response ────────────────────────────────────────────────────

class TestAmbiguityToResponse:
    def test_type_is_ambiguity(self, resolver):
        result = resolver.resolve("trend gp 8")
        assert isinstance(result, AmbiguityResult)
        resp = _ambiguity_to_response(result)
        assert resp["type"] == "ambiguity"

    def test_options_have_label_and_params(self, resolver):
        result = resolver.resolve("trend gp 8")
        resp = _ambiguity_to_response(result)
        for opt in resp["options"]:
            assert "label" in opt
            assert "params" in opt

    def test_prompt_is_non_empty(self, resolver):
        result = resolver.resolve("gp")
        resp = _ambiguity_to_response(result)
        assert isinstance(resp["prompt"], str)
        assert len(resp["prompt"]) > 0


# ── resolve_and_execute end-to-end ───────────────────────────────────────────

class TestResolveAndExecute:
    def test_value_result_with_data(self, resolver):
        rows = [_make_row("3", "Projection", 12_450_000, sheet="Projection")]
        resp = resolve_and_execute(
            query="projected gp",
            project_id=PROJECT,
            context_dict={"report_month": 2, "report_year": 2026},
            resolver=resolver,
            provider=InMemoryDataProvider(rows),
            heading_map=HEADING_MAP,
        )
        assert resp["type"] == "result"
        assert resp["rows"][0]["Value (HK$)"] == 12_450_000

    def test_missing_when_no_db_rows(self, resolver):
        resp = resolve_and_execute(
            query="projected gp",
            project_id=PROJECT,
            context_dict={"report_month": 2, "report_year": 2026},
            resolver=resolver,
            provider=InMemoryDataProvider([]),
            heading_map=HEADING_MAP,
        )
        assert resp["type"] == "missing"

    def test_ambiguity_without_financial_type(self, resolver):
        resp = resolve_and_execute(
            query="gp",
            project_id=PROJECT,
            context_dict={},
            resolver=resolver,
            provider=InMemoryDataProvider([]),
            heading_map=HEADING_MAP,
        )
        assert resp["type"] == "ambiguity"
        assert len(resp["options"]) > 0

    def test_selection_resolves_ambiguity(self, resolver):
        rows = [_make_row("3", "Projection", 5_000_000, sheet="Projection")]
        resp = resolve_and_execute(
            query="gp",
            project_id=PROJECT,
            context_dict={"report_month": 2, "report_year": 2026},
            selected_option_index=0,
            prior_options=[{
                "label": "Projection (Financial Status)",
                "params": {"financial_type": "Projection", "sheet_name": "Projection"},
            }],
            resolver=resolver,
            provider=InMemoryDataProvider(rows),
            heading_map=HEADING_MAP,
        )
        assert resp["type"] == "result"
        assert resp["rows"][0]["Value (HK$)"] == 5_000_000

    def test_shortcut_help_returns_info(self, resolver):
        resp = resolve_and_execute(
            query="shortcut",
            project_id=PROJECT,
            context_dict={},
            resolver=resolver,
            provider=InMemoryDataProvider([]),
            heading_map=HEADING_MAP,
        )
        assert resp["type"] == "info"
        assert resp["title"] == "Supported Shortcuts"

    def test_list_shortcut_returns_table(self, resolver):
        resp = resolve_and_execute(
            query="list",
            project_id=PROJECT,
            context_dict={},
            resolver=resolver,
            provider=InMemoryDataProvider([]),
            heading_map=HEADING_MAP,
        )
        assert resp["type"] == "result"
        assert len(resp["columns"]) > 0
