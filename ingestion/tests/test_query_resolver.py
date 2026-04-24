"""
Unit tests for query_resolver.py — Phase 7.

All tests run without DB or file I/O.
PRD example queries are covered with inline comments referencing PRD sections.
"""

import pytest

from src.query_resolver import (
    AmbiguityResult,
    ConversationContext,
    QueryResolver,
    ResolutionResult,
    ResolvedQuery,
    MONTHLY_FINANCIAL_TYPES,
    SNAPSHOT_SHEET,
    _detect_shortcuts,
    _format_period,
    _build_banner,
    _strip_trailing_number,
    _infer_sheet,
)

# ── Minimal CSV fixtures ──────────────────────────────────────────────────────

FINANCIAL_TYPE_CSV = """\
Raw_Financial_Type,Clean_Financial_Type,Acronyms
Budget Revision as at,Latest Budget,latest budget|budget|bt|revision|rev
Business Plan,Business Plan,bp|business plan
Audit Report (WIP),WIP,wip|audit|audit report
Projection as at,Projection,projected|projection
Committed Value / Cost as at,Committed Cost,committed|committed cost|committed value
Accrual\n(Before Retention) as at,Accrual,accrual|accrued
Cash Flow Actual received & paid as at,Cash Flow,cf|cashflow|cash flow|cash
Budget Tender,Budget Tender,tender|tender budget
"""

HEADING_CSV = """\
Item_Code,Data_Type,Friendly_Name,Category,Tier,Acronyms
1,Income,Total Income,Income,1,income|revenue|total income|item 1
1.1,Income - Original Contract Works,Original Contract Value,Income,2,ocw|original contract|contract value
1.7,Income - Claims,Claims Income,Income,2,claims|claims income|income claims
2,Less : Cost,Total Cost,Cost,1,cost|total cost|less cost|item 2
2.1,Less : Cost - Preliminaries,Preliminaries,Cost,2,prelim|preliminary|preliminaries|total prelim|prelims
2.2,Less : Cost - Materials,Total Materials,Cost,2,materials|material|material cost|total materials
2.2.15,Less : Cost - Materials - -Potential Savings (Materials),Material Savings,Cost,3,material savings|savings material|potential savings material
2.4,Less : Cost - Subcontractor,Total Subcontractor,Cost,2,subcon|sub|subbie|subcontractor|subcontractors|total subcon
2.7,Less : Cost - Allow for Contingencies,Contingency Reserve,Cost,2,contingency|contingency reserve
3,Gross Profit (Item 1.0-2.0) (Financial A/C),Gross Profit,Summary,1,gp|gross profit|profit|item 3
5,Gross Profit (Item 3.0-4.3),Gross Profit (after recon & overhead),Summary,1,gp after recon|net gp|gp after overhead|item 5
"""


@pytest.fixture(scope="module")
def resolver() -> QueryResolver:
    return QueryResolver.from_csv_strings(FINANCIAL_TYPE_CSV, HEADING_CSV)


# ── _detect_shortcuts ─────────────────────────────────────────────────────────

class TestDetectShortcuts:
    def test_trend(self):
        shortcuts, _ = _detect_shortcuts("trend gp 8")
        assert shortcuts == ["Trend"]

    def test_compare(self):
        shortcuts, _ = _detect_shortcuts("compare projected gp vs wip gp")
        assert "Compare" in shortcuts

    def test_trend_compare(self):
        shortcuts, _ = _detect_shortcuts("trend compare projection gp vs wip gp 8")
        assert "Trend" in shortcuts
        assert "Compare" in shortcuts

    def test_total(self):
        shortcuts, _ = _detect_shortcuts("total cost projected")
        assert shortcuts == ["Total"]

    def test_detail(self):
        shortcuts, _ = _detect_shortcuts("detail cash flow prelim")
        assert shortcuts == ["Detail"]

    def test_risk_standalone(self):
        shortcuts, _ = _detect_shortcuts("risk")
        assert shortcuts == ["Risk"]

    def test_list_standalone(self):
        shortcuts, _ = _detect_shortcuts("list")
        assert shortcuts == ["List"]

    def test_type_standalone(self):
        shortcuts, _ = _detect_shortcuts("type")
        assert shortcuts == ["Type"]

    def test_shortcut_keyword(self):
        shortcuts, _ = _detect_shortcuts("shortcut")
        assert shortcuts == ["Shortcut"]

    def test_cash_flow_standalone(self):
        shortcuts, _ = _detect_shortcuts("cash flow")
        assert shortcuts == ["Cash Flow Shortcut"]

    def test_cash_flow_not_shortcut_after_detail(self):
        # "detail" is the primary shortcut; "cash flow" is a reference, not a shortcut
        shortcuts, _ = _detect_shortcuts("detail cash flow prelim")
        assert shortcuts == ["Detail"]
        assert "Cash Flow Shortcut" not in shortcuts

    def test_analyse_variant(self):
        shortcuts, _ = _detect_shortcuts("analyse income")
        assert shortcuts == ["Analyze"]

    def test_removes_keywords_from_remaining(self):
        _, remaining = _detect_shortcuts("trend gp 8")
        assert "trend" not in remaining

    def test_vs_implies_compare(self):
        shortcuts, _ = _detect_shortcuts("projected gp vs wip gp")
        assert "Compare" in shortcuts


# ── PRD §3.2 example queries ──────────────────────────────────────────────────

class TestPRDExampleQueries:

    # "projected gp" — PRD §15.2.C: no month, ambiguous snapshot vs monthly
    def test_projected_gp_is_ambiguous(self, resolver):
        result = resolver.resolve("projected gp")
        assert isinstance(result, AmbiguityResult)
        assert result.is_ambiguous
        labels = [i.label for i in result.interpretations]
        # Must offer at least Financial Status snapshot option
        assert any("Financial Status" in lbl or "snapshot" in lbl.lower() for lbl in labels)

    # "projected gp" with month in context → no ambiguity
    def test_projected_gp_with_context_month(self, resolver):
        ctx = ConversationContext(report_month=2, report_year=2026)
        result = resolver.resolve("projected gp", ctx)
        assert isinstance(result, ResolutionResult)
        assert result.resolved.financial_type == "Projection"
        assert result.resolved.data_type is not None  # Gross Profit resolved

    # "compare projected gp vs wip gp" — PRD §13.5
    def test_compare_projected_vs_wip(self, resolver):
        ctx = ConversationContext(report_month=2, report_year=2026)
        result = resolver.resolve("compare projected gp vs wip gp", ctx)
        assert isinstance(result, ResolutionResult)
        r = result.resolved
        assert r.shortcut == "Compare"
        assert r.compare_a is not None
        assert r.compare_b is not None
        assert r.compare_a.financial_type == "Projection"
        assert r.compare_b.financial_type == "WIP"
        # Both sides should resolve GP
        assert r.compare_a.data_type is not None
        assert r.compare_b.data_type is not None

    # "trend compare projection gp vs wip gp 8" — PRD §14
    def test_trend_compare_8(self, resolver):
        ctx = ConversationContext(report_month=2, report_year=2026)
        result = resolver.resolve("trend compare projection gp vs wip gp 8", ctx)
        assert isinstance(result, ResolutionResult)
        r = result.resolved
        assert r.shortcut == "Trend"
        assert r.shortcut_b == "Compare"
        assert r.num_months == 8
        assert r.compare_a is not None
        assert r.compare_b is not None

    # "total cost projected" — PRD §13.8
    def test_total_cost_projected(self, resolver):
        ctx = ConversationContext(report_month=2, report_year=2026)
        result = resolver.resolve("total cost projected", ctx)
        assert isinstance(result, ResolutionResult)
        r = result.resolved
        assert r.shortcut == "Total"
        assert r.financial_type == "Projection"

    # "total prelim bp" — PRD §13.8
    def test_total_prelim_bp(self, resolver):
        ctx = ConversationContext(report_month=2, report_year=2026)
        result = resolver.resolve("total prelim bp", ctx)
        assert isinstance(result, ResolutionResult)
        r = result.resolved
        assert r.shortcut == "Total"
        assert r.financial_type == "Business Plan"
        assert r.data_type is not None  # Preliminaries

    # "detail cash flow prelim" — PRD §13.9
    def test_detail_cash_flow_prelim(self, resolver):
        ctx = ConversationContext(report_month=2, report_year=2026)
        result = resolver.resolve("detail cash flow prelim", ctx)
        assert isinstance(result, ResolutionResult)
        r = result.resolved
        assert r.shortcut == "Detail"
        assert r.financial_type == "Cash Flow"
        assert r.data_type is not None  # Preliminaries

    # "risk" — PRD §13.10
    def test_risk_shortcut(self, resolver):
        result = resolver.resolve("risk")
        assert isinstance(result, ResolutionResult)
        assert result.resolved.shortcut == "Risk"

    # "list" — PRD §13.7
    def test_list_shortcut(self, resolver):
        result = resolver.resolve("list")
        assert isinstance(result, ResolutionResult)
        assert result.resolved.shortcut == "List"

    # "list 2.2" — PRD §13.7: list sub-items under 2.2
    def test_list_item_code(self, resolver):
        result = resolver.resolve("list 2.2")
        assert isinstance(result, ResolutionResult)
        r = result.resolved
        assert r.shortcut == "List"
        assert r.item_code == "2.2"

    # "committed prelim 8" — PRD §3.2: committed + prelim + number 8
    def test_committed_prelim_8(self, resolver):
        # With no context, month=8 but no sheet → ambiguity between snapshot and monthly
        # OR: "committed" resolves financial_type → Committed Cost + month=8 → monthly sheet
        ctx = ConversationContext(report_year=2026)
        result = resolver.resolve("committed prelim 8", ctx)
        # committed + month present → should resolve to Committed Cost monthly sheet
        assert isinstance(result, ResolutionResult)
        r = result.resolved
        assert r.financial_type == "Committed Cost"
        assert r.month == 8
        assert r.sheet_name == "Committed Cost"

    # "prelim oct" — PRD §15.2.F: month present, no financial type → ambiguous
    def test_prelim_oct_ambiguous(self, resolver):
        result = resolver.resolve("prelim oct")
        assert isinstance(result, AmbiguityResult)
        assert result.is_ambiguous
        # Should offer all monthly financial types
        labels = [i.label for i in result.interpretations]
        assert len(result.interpretations) >= 2

    # "trend gp 8" — PRD §15.2.D: trend, no financial type → ambiguous
    def test_trend_gp_8_ambiguous(self, resolver):
        result = resolver.resolve("trend gp 8")
        assert isinstance(result, AmbiguityResult)
        assert result.is_ambiguous
        assert "Trend" in result.reason or "financial type" in result.reason.lower()
        # Must offer all monthly financial types as options
        assert len(result.interpretations) == len(MONTHLY_FINANCIAL_TYPES)

    # "type" — PRD §13.12
    def test_type_shortcut(self, resolver):
        result = resolver.resolve("type")
        assert isinstance(result, ResolutionResult)
        assert result.resolved.shortcut == "Type"

    # "shortcut" — PRD §13.3
    def test_shortcut_keyword(self, resolver):
        result = resolver.resolve("shortcut")
        assert isinstance(result, ResolutionResult)
        assert result.resolved.shortcut == "Shortcut"

    # "gp" — PRD §15.2.E: no financial type → show options
    def test_gp_standalone_ambiguous(self, resolver):
        result = resolver.resolve("gp")
        assert isinstance(result, AmbiguityResult)

    # "prelim oct" using context financial_type → resolves cleanly
    def test_prelim_oct_with_context_ft(self, resolver):
        ctx = ConversationContext(financial_type="Projection", report_year=2026)
        result = resolver.resolve("prelim oct", ctx)
        assert isinstance(result, ResolutionResult)
        r = result.resolved
        assert r.financial_type == "Projection"
        assert r.month == 10

    # Cash Flow shortcut standalone
    def test_cash_flow_shortcut(self, resolver):
        result = resolver.resolve("cash flow")
        assert isinstance(result, ResolutionResult)
        assert result.resolved.shortcut == "Cash Flow Shortcut"


# ── Context memory rules ──────────────────────────────────────────────────────

class TestContextMemory:

    def test_project_inherited_from_context(self, resolver):
        ctx = ConversationContext(
            project_id="proj-1", project_code="969", project_name="Hiu Ming Street",
            report_month=2, report_year=2026,
        )
        result = resolver.resolve("projected gp", ctx)
        # Even if ambiguous on sheet, project should be passed through
        if isinstance(result, AmbiguityResult):
            assert result.partial.project_code == "969"
        else:
            assert result.resolved.project_code == "969"

    def test_month_defaults_to_report_period(self, resolver):
        ctx = ConversationContext(
            financial_type="Projection", report_month=2, report_year=2026
        )
        result = resolver.resolve("projected gp", ctx)
        assert isinstance(result, ResolutionResult)
        assert result.resolved.month == 2
        assert result.resolved.year == 2026
        assert "month (report default)" in result.resolved.context_used

    def test_financial_type_inherited(self, resolver):
        ctx = ConversationContext(financial_type="Accrual", report_month=2, report_year=2026)
        result = resolver.resolve("prelim", ctx)
        assert isinstance(result, ResolutionResult)
        r = result.resolved
        assert r.financial_type == "Accrual"
        assert "financial_type" in r.context_used

    def test_context_not_reused_when_ambiguous(self, resolver):
        # No context → standalone "gp" should still be ambiguous
        result = resolver.resolve("gp")
        assert isinstance(result, AmbiguityResult)


# ── Month and year parsing — PRD §9.4 ────────────────────────────────────────

class TestMonthYearParsing:

    def test_month_by_name(self, resolver):
        ctx = ConversationContext(financial_type="Projection", report_year=2026)
        result = resolver.resolve("projected gp october", ctx)
        assert isinstance(result, ResolutionResult)
        assert result.resolved.month == 10

    def test_month_abbreviation(self, resolver):
        ctx = ConversationContext(financial_type="Projection", report_year=2026)
        result = resolver.resolve("projected gp oct", ctx)
        assert isinstance(result, ResolutionResult)
        assert result.resolved.month == 10

    def test_year_parsed(self, resolver):
        ctx = ConversationContext(financial_type="Projection")
        result = resolver.resolve("projected gp feb 2026", ctx)
        assert isinstance(result, ResolutionResult)
        assert result.resolved.month == 2
        assert result.resolved.year == 2026

    def test_trend_number_is_num_months(self, resolver):
        ctx = ConversationContext(financial_type="Projection", report_month=2, report_year=2026)
        result = resolver.resolve("trend projected gp 8", ctx)
        assert isinstance(result, ResolutionResult)
        assert result.resolved.num_months == 8

    def test_trend_default_6_months(self, resolver):
        ctx = ConversationContext(financial_type="Projection", report_month=2, report_year=2026)
        result = resolver.resolve("trend projected gp", ctx)
        assert isinstance(result, ResolutionResult)
        assert result.resolved.num_months == 6


# ── Trend + Financial Status warning — PRD §8.1, §13.6 ───────────────────────

class TestTrendFinancialStatusWarning:

    def test_trend_against_fs_adds_warning(self, resolver):
        # WIP is not a monthly sheet — it exists only in Financial Status.
        # Trending against FS (which has no month-by-month history) should warn.
        ctx = ConversationContext(report_month=2, report_year=2026)
        result = resolver.resolve("trend wip gp", ctx)
        assert isinstance(result, ResolutionResult)
        r = result.resolved
        assert r.sheet_name == "Financial Status"
        assert any("Financial Status" in w for w in r.warnings)


# ── Ambiguity ranking — PRD §10.3 ────────────────────────────────────────────

class TestAmbiguityRanking:

    def test_interpretations_ranked(self, resolver):
        result = resolver.resolve("trend gp 8")
        assert isinstance(result, AmbiguityResult)
        ranks = [i.rank for i in result.interpretations]
        assert ranks == sorted(ranks)

    def test_max_5_interpretations(self, resolver):
        result = resolver.resolve("gp")
        assert isinstance(result, AmbiguityResult)
        assert len(result.interpretations) <= 5

    def test_partial_included_in_ambiguity(self, resolver):
        result = resolver.resolve("trend gp 8")
        assert isinstance(result, AmbiguityResult)
        assert result.partial is not None
        assert result.partial.shortcut == "Trend"


# ── Interpretation banner — PRD §9.5 ─────────────────────────────────────────

class TestBanner:

    def test_banner_fields_present(self, resolver):
        ctx = ConversationContext(
            project_code="969", project_name="Hiu Ming Street",
            financial_type="Projection", report_month=2, report_year=2026,
        )
        result = resolver.resolve("projected gp", ctx)
        assert isinstance(result, ResolutionResult)
        banner = result.resolved.banner
        assert "project" in banner
        assert "sheet" in banner
        assert "financial_type" in banner
        assert "data_type" in banner
        assert "period" in banner

    def test_banner_period_format(self):
        assert _format_period(2, 2026) == "Feb 2026"
        assert _format_period(None, 2026) == "2026"
        assert _format_period(None, None) == "—"

    def test_banner_project_combined(self, resolver):
        ctx = ConversationContext(
            project_id="x", project_code="969", project_name="Hiu Ming Street",
            financial_type="Projection", report_month=2, report_year=2026,
        )
        result = resolver.resolve("projected gp", ctx)
        assert isinstance(result, ResolutionResult)
        assert "969" in result.resolved.banner["project"]
        assert "Hiu Ming Street" in result.resolved.banner["project"]


# ── No-guess principle — PRD §7.1, §10.1 ─────────────────────────────────────

class TestNoGuess:

    def test_never_guesses_financial_type(self, resolver):
        # "gp" alone: no financial type → must return ambiguity, never guess
        result = resolver.resolve("gp")
        assert isinstance(result, AmbiguityResult)

    def test_never_guesses_monthly_sheet(self, resolver):
        # "prelim oct": month present, no financial type → ambiguity
        result = resolver.resolve("prelim oct")
        assert isinstance(result, AmbiguityResult)

    def test_explicit_shortcut_detection_only(self, resolver):
        # PRD §13.1: "committed prelim" (no trend keyword) → NOT trend mode
        ctx = ConversationContext(report_month=2, report_year=2026)
        result = resolver.resolve("committed prelim", ctx)
        # Should be ambiguous (snapshot vs monthly, no month) or resolved to snapshot
        # — must NOT set num_months
        if isinstance(result, ResolutionResult):
            assert result.resolved.num_months is None
        else:
            assert result.partial is None or result.partial.num_months is None


# ── _strip_trailing_number ────────────────────────────────────────────────────

class TestStripTrailingNumber:
    def test_strips_number_at_end(self):
        text, n = _strip_trailing_number("trend gp 8")
        assert n == 8
        assert "8" not in text

    def test_no_number_returns_none(self):
        text, n = _strip_trailing_number("trend gp")
        assert n is None
        assert text == "trend gp"

    def test_number_in_middle_not_stripped(self):
        _, n = _strip_trailing_number("trend 8 gp")
        assert n is None

    def test_strips_multi_digit_number(self):
        _, n = _strip_trailing_number("trend gp 12")
        assert n == 12


# ── _infer_sheet ──────────────────────────────────────────────────────────────

class TestInferSheet:
    def test_monthly_ft_with_month_infers_monthly_sheet(self):
        r = ResolvedQuery(financial_type="Projection", month=2)
        _infer_sheet(r)
        assert r.sheet_name == "Projection"

    def test_monthly_ft_without_month_leaves_sheet_none(self):
        r = ResolvedQuery(financial_type="Projection", month=None)
        _infer_sheet(r)
        assert r.sheet_name is None

    def test_snapshot_ft_infers_financial_status(self):
        r = ResolvedQuery(financial_type="WIP")
        _infer_sheet(r)
        assert r.sheet_name == "Financial Status"

    def test_no_ft_leaves_sheet_none(self):
        r = ResolvedQuery(financial_type=None)
        _infer_sheet(r)
        assert r.sheet_name is None

    def test_existing_sheet_not_overwritten(self):
        r = ResolvedQuery(financial_type="Projection", month=2, sheet_name="Financial Status")
        _infer_sheet(r)
        assert r.sheet_name == "Financial Status"  # unchanged


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_query_does_not_crash(self, resolver):
        result = resolver.resolve("")
        assert result is not None

    def test_whitespace_only_query_does_not_crash(self, resolver):
        result = resolver.resolve("   ")
        assert result is not None

    def test_numbers_only_does_not_crash(self, resolver):
        result = resolver.resolve("123")
        assert result is not None

    def test_shortcut_plural_form_detected(self):
        shortcuts, _ = _detect_shortcuts("shortcuts")
        assert shortcuts == ["Shortcut"]

    def test_year_with_month_both_parsed(self, resolver):
        ctx = ConversationContext(financial_type="Projection")
        result = resolver.resolve("projected gp feb 2025", ctx)
        assert isinstance(result, ResolutionResult)
        assert result.resolved.month == 2
        assert result.resolved.year == 2025

    def test_context_month_suppresses_snapshot_vs_monthly_ambiguity(self, resolver):
        ctx = ConversationContext(financial_type="Projection", report_month=3, report_year=2026)
        result = resolver.resolve("projected gp", ctx)
        assert isinstance(result, ResolutionResult)

    def test_item_code_lookup_exact_match(self, resolver):
        ctx = ConversationContext(report_month=2, report_year=2026)
        result = resolver.resolve("projected 2.2", ctx)
        assert isinstance(result, ResolutionResult)
        assert result.resolved.item_code == "2.2"
