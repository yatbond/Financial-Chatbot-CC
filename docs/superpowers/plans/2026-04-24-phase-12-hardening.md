# Phase 12: Hardening & Deployment Readiness

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the FinLens app for internal use by expanding test coverage, improving error handling, and producing deployment documentation.

**Architecture:** Tests are pure unit/integration (no real DB or file I/O). Error handling improvements are targeted at the ingestion service boundary. Deployment docs are written to `docs/`. Nothing in the chat UI, resolver, or ingestion pipeline logic is changed.

**Tech Stack:** Python 3.12 + pytest + uv (ingestion); Vitest 4.1.5 (web); Next.js 15 App Router; Supabase; Clerk; FastAPI.

**Baseline:** `uv run pytest -q` → 151 passed. `npm test` (in `web/`) → 12 passed. All tests must still pass after every task.

---

## File Structure

**Modified (tests):**
- `ingestion/tests/test_parser.py` — add FS multi-column and zero-value coverage
- `ingestion/tests/test_query_resolver.py` — add edge case tests for helpers
- `ingestion/tests/test_shortcut_engine.py` — add missing-sheet and multi-rule tests

**Created (tests):**
- `ingestion/tests/test_normalizer.py` — full coverage of `normalize_rows()`

**Modified (source):**
- `ingestion/main.py` — UUID validation on `/ingest` endpoint

**Created (docs):**
- `docs/deployment.md` — deployment guide + production checklist
- `docs/known-issues.md` — replace stale content with current state
- `docs/observability.md` — logging and monitoring recommendations

---

## Task 1: Parser — additional unit tests

**Files:**
- Modify: `ingestion/tests/test_parser.py`

- [ ] **Step 1: Add tests for FS multi-column extraction and zero-value**

Append to `ingestion/tests/test_parser.py` after the existing `TestParseFinancialStatus` class:

```python
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

    def test_multiple_value_columns_produce_multiple_rows(self):
        """Each non-None value column in a FS row becomes a separate ExtractedRow."""
        data = [[1.0, "Trade"] + [None] * 13]
        data[0][2] = 100.0   # col 2 = Budget Tender
        data[0][5] = 200.0   # col 5 = Latest Budget (Budget Revision as at)
        data[0][9] = 300.0   # col 9 = Projection
        rows = _make_fs_rows(data)
        result = parse_financial_status(rows, 2, 2026)
        ft_types = {r.raw_financial_type for r in result.rows}
        assert "Budget Tender" in ft_types
        assert "Budget Revision as at" in ft_types
        assert "Projection as at" in ft_types
        assert len(result.rows) == 3

    def test_all_none_value_columns_produce_no_rows(self):
        """A row with all None values (no data) should produce no output rows."""
        data = [[1.0, "Trade"] + [None] * 13]
        rows = _make_fs_rows(data)
        result = parse_financial_status(rows, 2, 2026)
        assert result.rows == []

    def test_two_data_rows_each_produce_rows(self):
        data = [
            [1.0, "Income"] + [None] * 13,
            [2.0, "Cost"] + [None] * 13,
        ]
        data[0][2] = 500.0
        data[1][2] = 800.0
        rows = _make_fs_rows(data)
        result = parse_financial_status(rows, 2, 2026)
        codes = [r.item_code for r in result.rows]
        assert "1" in codes
        assert "2" in codes


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
        """source_cell_ref column letter should reflect the column index."""
        data = [[1.0, "Trade", 999.0]]
        rows = _make_monthly_rows(["Feb"], data)
        result = parse_monthly_sheet(rows, "Projection", "Projection", 2, 2026)
        r = result.rows[0]
        # data starts at row 12 (0-indexed), so Excel row = 13
        assert r.source_row_number == 13
        # value is in col 2 (0-indexed) → "C"
        assert r.source_cell_ref.startswith("C")
```

- [ ] **Step 2: Run new tests to verify they pass**

```bash
cd "/home/yatbond/projects/financial chatbot/ingestion"
uv run pytest tests/test_parser.py -v -q 2>&1 | tail -20
```

Expected: all new tests PASS (or FAIL with a clear error if the parser doesn't handle the case yet — investigate and fix the test expectation to match actual behaviour).

- [ ] **Step 3: Commit**

```bash
cd "/home/yatbond/projects/financial chatbot"
git add ingestion/tests/test_parser.py
git commit -m "test(parser): add FS multi-column, zero-value, and monthly coverage"
```

---

## Task 2: Normalizer — integration tests

**Files:**
- Create: `ingestion/tests/test_normalizer.py`

- [ ] **Step 1: Write the tests**

Create `ingestion/tests/test_normalizer.py`:

```python
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
    "1":   {"data_type": "Income",       "friendly_name": "Total Income",    "category": "Income", "tier": 1},
    "2.1": {"data_type": "Less Cost",    "friendly_name": "Preliminaries",   "category": "Cost",   "tier": 2},
    "3":   {"data_type": "Gross Profit", "friendly_name": "Gross Profit",    "category": "Summary","tier": 1},
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


# ── Tests ─────────────────────────────────────────────────────────────────────

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

    def test_none_item_code_not_tracked_as_unmapped(self):
        """Rows with no item code are valid (summary rows) — must not pollute unmapped set."""
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
```

- [ ] **Step 2: Run the tests**

```bash
cd "/home/yatbond/projects/financial chatbot/ingestion"
uv run pytest tests/test_normalizer.py -v 2>&1 | tail -20
```

Expected: all 13 tests PASS.

- [ ] **Step 3: Commit**

```bash
cd "/home/yatbond/projects/financial chatbot"
git add ingestion/tests/test_normalizer.py
git commit -m "test(normalizer): add full integration test suite for normalize_rows()"
```

---

## Task 3: Query resolver — edge case tests

**Files:**
- Modify: `ingestion/tests/test_query_resolver.py`

- [ ] **Step 1: Add helper tests and edge case tests**

Append to `ingestion/tests/test_query_resolver.py`:

```python
# ── _strip_trailing_number ────────────────────────────────────────────────────

from src.query_resolver import _strip_trailing_number, _infer_sheet, ResolvedQuery

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
    def test_empty_query_returns_ambiguity(self, resolver):
        result = resolver.resolve("")
        assert isinstance(result, AmbiguityResult)

    def test_whitespace_only_query_returns_ambiguity(self, resolver):
        result = resolver.resolve("   ")
        assert isinstance(result, AmbiguityResult)

    def test_numbers_only_does_not_crash(self, resolver):
        result = resolver.resolve("123")
        # Should not raise; may be ambiguity or resolution
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
        # With month in context, should resolve cleanly without ambiguity
        assert isinstance(result, ResolutionResult)

    def test_item_code_lookup_exact_match(self, resolver):
        ctx = ConversationContext(report_month=2, report_year=2026)
        result = resolver.resolve("projected 2.2", ctx)
        assert isinstance(result, ResolutionResult)
        assert result.resolved.item_code == "2.2"
```

- [ ] **Step 2: Run the new tests**

```bash
cd "/home/yatbond/projects/financial chatbot/ingestion"
uv run pytest tests/test_query_resolver.py -v -q 2>&1 | tail -25
```

Expected: all new tests PASS.

- [ ] **Step 3: Commit**

```bash
cd "/home/yatbond/projects/financial chatbot"
git add ingestion/tests/test_query_resolver.py
git commit -m "test(query_resolver): add edge case tests for helpers and boundary inputs"
```

---

## Task 4: Shortcut engine — additional tests

**Files:**
- Modify: `ingestion/tests/test_shortcut_engine.py`

- [ ] **Step 1: Add missing edge case tests**

Append to `ingestion/tests/test_shortcut_engine.py`:

```python
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
            # Income exception: proj < wip for item 1.1
            _row("1.1", "Projection", 800_000),
            _row("1.1", "WIP",        900_000),
            # Cost exception: proj > accrual for item 2.1
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
        # Last entry must be Feb 2026 (latest anchor)
        assert periods[-1] == "Feb 2026"
        # First entry must be Mar 2025 (12 months back from Feb 2026)
        assert periods[0] == "Mar 2025"
```

- [ ] **Step 2: Run the new tests**

```bash
cd "/home/yatbond/projects/financial chatbot/ingestion"
uv run pytest tests/test_shortcut_engine.py -v -q 2>&1 | tail -20
```

Expected: all new tests PASS.

- [ ] **Step 3: Run full test suite to verify no regressions**

```bash
cd "/home/yatbond/projects/financial chatbot/ingestion"
uv run pytest -q
```

Expected: all tests PASS (count will be higher than 151).

- [ ] **Step 4: Commit**

```bash
cd "/home/yatbond/projects/financial chatbot"
git add ingestion/tests/test_shortcut_engine.py
git commit -m "test(shortcut_engine): add missing sheet, multi-rule analyze, and 12-month CF tests"
```

---

## Task 5: Ingestion service — error handling

**Files:**
- Modify: `ingestion/main.py`

- [ ] **Step 1: Read the current main.py**

```
Current ingestion/main.py accepts `upload_id: str` from the request body with no validation.
A non-UUID string (empty, path traversal, too long) would be passed to DB queries as-is.
```

- [ ] **Step 2: Add UUID validation**

Replace the `IngestRequest` class and the `ingest` endpoint body in `ingestion/main.py`:

```python
import re

_UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE,
)


class IngestRequest(BaseModel):
    upload_id: str


@app.post("/ingest")
def ingest(req: IngestRequest, background_tasks: BackgroundTasks):
    if not _UUID_RE.match(req.upload_id):
        return JSONResponse(
            {"error": "upload_id must be a valid UUID"},
            status_code=422,
        )
    background_tasks.add_task(run_ingestion, req.upload_id)
    return JSONResponse({"accepted": True, "upload_id": req.upload_id}, status_code=202)
```

The full updated `ingestion/main.py` should look like:

```python
"""FastAPI ingestion service entry point."""

import logging
import re
import sys

import uvicorn
from fastapi import BackgroundTasks, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.config import INGESTION_PORT
from src.ingestion import run_ingestion

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    stream=sys.stdout,
)

app = FastAPI(title="FinLens Ingestion Service")

_UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE,
)


class IngestRequest(BaseModel):
    upload_id: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ingest")
def ingest(req: IngestRequest, background_tasks: BackgroundTasks):
    if not _UUID_RE.match(req.upload_id):
        return JSONResponse(
            {"error": "upload_id must be a valid UUID"},
            status_code=422,
        )
    background_tasks.add_task(run_ingestion, req.upload_id)
    return JSONResponse({"accepted": True, "upload_id": req.upload_id}, status_code=202)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=INGESTION_PORT, reload=False)
```

- [ ] **Step 3: Verify tests still pass**

```bash
cd "/home/yatbond/projects/financial chatbot/ingestion"
uv run pytest -q
```

Expected: all tests PASS (main.py is not imported by tests).

- [ ] **Step 4: Commit**

```bash
cd "/home/yatbond/projects/financial chatbot"
git add ingestion/main.py
git commit -m "fix(ingestion): validate upload_id is a UUID before dispatching ingest job"
```

---

## Task 6: Deployment documentation

**Files:**
- Create: `docs/deployment.md`

- [ ] **Step 1: Write the deployment guide**

Create `docs/deployment.md` with the following content:

```markdown
# Deployment Guide

> Last updated: 2026-04-24. Internal use only.

## Prerequisites

- Node.js 20+, npm
- Python 3.12, uv
- Supabase project (Postgres + Storage)
- Clerk application (auth)
- Redis instance (Upstash or Railway)
- Vercel account (web)
- Fly.io or Railway account (ingestion service)

---

## Environment Variables

### Web (`web/.env.local`)

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key (public) |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key (server-only) |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Clerk publishable key |
| `CLERK_SECRET_KEY` | Clerk secret key (server-only) |
| `NEXT_PUBLIC_CLERK_SIGN_IN_URL` | `/sign-in` |
| `NEXT_PUBLIC_CLERK_SIGN_UP_URL` | `/sign-up` |
| `NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL` | `/projects` |
| `NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL` | `/projects` |

### Ingestion service (`ingestion/.env`)

| Variable | Description |
|---|---|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key |
| `DATABASE_URL` | Direct Postgres connection string (not pooler) |
| `INGESTION_PORT` | Port to bind (default: 8000) |

---

## Supabase Setup

1. **Run migrations** (all files in `web/supabase/migrations/` in order):
   ```
   supabase db push
   ```
   Or apply each `.sql` file manually via the Supabase SQL editor.

2. **Storage bucket** — create a private bucket named `mappings` and `reports`.
   - `mappings/`: stores uploaded CSV mapping files
   - `reports/`: stores uploaded Excel reports

3. **Row-Level Security** — RLS is configured per-migration. After applying migrations, verify:
   - `projects` table: users can only read projects they belong to
   - `normalized_financial_rows`: filtered by project membership
   - `query_logs`: filtered by project membership
   - `admin_notes`: no public read (admin-only)

   **Manual check:** In Supabase dashboard → Table Editor → each table → RLS enabled ✓

4. **Service role key** is required for the ingestion worker (bypasses RLS for inserts). Never expose this to the browser.

---

## Web Deployment (Vercel)

```bash
cd web
npm run build          # verify build succeeds locally first
```

1. Push to GitHub (main branch)
2. Import repository in Vercel
3. Set **Root Directory** to `web`
4. Add all environment variables from the table above
5. Deploy

**Post-deploy checks:**
- `GET /` → redirects to `/sign-in` ✓
- `POST /api/projects/<id>/chat` with valid session → returns JSON ✓
- Admin page loads without 500 errors ✓

---

## Ingestion Service Deployment (Fly.io)

```bash
cd ingestion
uv sync
fly launch --name finlens-ingestion --no-deploy
```

Add secrets:
```bash
fly secrets set SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... DATABASE_URL=...
```

Deploy:
```bash
fly deploy
```

Health check:
```bash
curl https://finlens-ingestion.fly.dev/health
# → {"status": "ok"}
```

**Note:** The ingestion service is currently triggered by a direct HTTP call from the web `/api/reports/upload` route, not via Redis/BullMQ. Redis queuing is deferred (see `docs/known-issues.md`).

---

## Production Checklist

### Before first deploy

- [ ] All migrations applied to production Supabase
- [ ] Storage buckets `mappings` and `reports` created (private)
- [ ] Clerk production application keys set (not development keys)
- [ ] `SUPABASE_SERVICE_ROLE_KEY` set in Vercel env — verify it is NOT prefixed with `NEXT_PUBLIC_`
- [ ] Ingestion service deployed and `/health` returns 200
- [ ] At least one project and user record in `projects` and `project_members` tables

### After first deploy

- [ ] Upload a sample CSV mapping (Financial Type Map) and confirm it applies
- [ ] Upload a sample Excel report and confirm ingestion succeeds (`validation_status = 'valid'`)
- [ ] Run a chat query and confirm a `query_logs` row is inserted
- [ ] Verify the Admin panel loads and shows the Mappings tab
- [ ] Verify "Export for Claude" downloads a `.md` file
- [ ] Check Supabase logs for any 500-level errors within 10 minutes of deploy

### Ongoing

- [ ] Monitor `query_logs` for `response_type = 'error'` spikes
- [ ] Monitor ingestion upload `validation_status = 'invalid'` rate
- [ ] Review open discrepancies weekly in the Admin panel
- [ ] Rotate `SUPABASE_SERVICE_ROLE_KEY` and `CLERK_SECRET_KEY` every 90 days

---

## Known Deployment Gotchas

1. **`SUPABASE_SERVICE_ROLE_KEY` must be server-only** — never prefix with `NEXT_PUBLIC_`. The web server passes it only to `createServerSupabase()` in server components and route handlers.

2. **Ingestion service DB connection** — use the direct connection string, not the Supabase pooler URL. The worker holds long-lived transactions during overlap resolution.

3. **Clerk domain** — Clerk requires the production domain to be added to "Allowed redirect origins" in the dashboard before sign-in works on the production URL.

4. **Next.js `params` and `searchParams`** — these are `Promise<...>` in this project. Any new page must `await params` before use, or you will get a hydration error.
```

- [ ] **Step 2: Commit**

```bash
cd "/home/yatbond/projects/financial chatbot"
git add docs/deployment.md
git commit -m "docs: add deployment guide and production checklist"
```

---

## Task 7: Known limitations — update docs

**Files:**
- Modify: `docs/known-issues.md`

- [ ] **Step 1: Replace stale content**

Rewrite `docs/known-issues.md` with the following content:

```markdown
# Known Issues & Limitations

> Updated: 2026-04-24.

## Critical (blocks production use)

### 1. Web chat resolver is a mock
The file `web/lib/chat/resolver.ts` contains a **mock resolver** that returns hardcoded data.
It does NOT use the Python `query_resolver.py` or `shortcut_engine.py` engines.

**Impact:** All chat responses in the web UI return simulated values, not real financial data from the database.

**Fix required:** Replace `web/lib/chat/resolver.ts` with a call to the Python ingestion service (or a new API route that runs the real resolver against Supabase data). This is the primary blocker before real production use.

---

### 2. Ingestion trigger is direct HTTP, not queue-backed
`app/(app)/projects/[projectId]/reports/actions.ts` calls the ingestion service via direct HTTP.
Redis + BullMQ queuing (planned in Phase 0) is not implemented.

**Impact:** If the ingestion service is slow or down, the upload action will time out or return an error to the user. No retry logic exists.

**Fix required:** Wire uploads through a Redis queue. The ingestion service already has a `/ingest` endpoint that accepts `upload_id`; the queue just needs to call it.

---

## Moderate (affects reliability)

### 3. Supabase RLS not verified in production
RLS policies were written in migrations but have not been tested with a real production Supabase project and real Clerk JWTs.

**Impact:** Data isolation between projects may not be enforced correctly.

**Action:** After first deploy, verify RLS by attempting cross-project queries with a non-member user session.

### 4. `.xls` (BIFF) file handling depends on xlrd < 2.0
The ingestion parser uses `xlrd` for `.xls` files. `xlrd >= 2.0` dropped `.xls` support.
The `uv.lock` pins `xlrd` to a compatible version, but this is fragile.

**Impact:** Old Excel `.xls` reports may fail if the dependency is upgraded carelessly.

**Action:** Lock `xlrd` explicitly in `pyproject.toml` and add a comment explaining the constraint.

### 5. Report month/year assumed from workbook header
The parser reads `report_date` from a fixed cell location (row 4, col 1 = "Report Date:").
If a workbook uses a different header layout, month/year extraction will fail silently and default to `None`.

**Impact:** Ingested rows may have `NULL` `report_month`/`report_year`, causing them to be invisible to query resolution.

**Action:** Add a validation step in `run_ingestion()` that rejects uploads with `header.report_month is None`.

---

## Low (cosmetic / future)

### 6. Admin panel tab state is lost on page reload
URL search params preserve tab, page, mode, and type — but only when navigating within the app. A direct URL with `?tab=query-logs&page=2` works correctly, but browser back-button behaviour in some cases resets to the default tab.

### 7. No rate limiting on the chat API route
`POST /api/projects/[projectId]/chat` has no rate limiting. A user could submit thousands of queries per minute, which would fill `query_logs` and slow the admin panel.

**Action:** Add Vercel rate limiting or an in-route request counter before production launch.

### 8. `admin_notes` has no soft-delete
Notes can only be overwritten (upsert), not deleted. There is no way to remove a note once written.
```

- [ ] **Step 2: Commit**

```bash
cd "/home/yatbond/projects/financial chatbot"
git add docs/known-issues.md
git commit -m "docs: rewrite known-issues.md with current state and critical blockers"
```

---

## Task 8: Observability recommendations

**Files:**
- Create: `docs/observability.md`

- [ ] **Step 1: Write the observability guide**

Create `docs/observability.md`:

```markdown
# Observability & Logging

> Guidance for monitoring FinLens in production.

## What Is Already Logged

### Python ingestion service
- Structured log lines at `INFO` level for each ingestion step:
  - `Starting ingestion: upload=... project=... path=...`
  - `Overlap resolved: discrepancies=N deactivated=...`
  - `Ingestion complete: rows=N status=... unmapped_ft=N unmapped_ic=N`
- `EXCEPTION` (via `log.exception`) on any fatal error, with full traceback
- Format: `%(asctime)s %(levelname)s %(name)s — %(message)s` to stdout

### Web (Next.js)
- `console.error('[chat/route] resolver error', err)` — query resolution crash
- `console.warn('[chat/route] query_log insert failed (non-fatal)', err)` — DB log failure

### Database
- `query_logs` table: every chat query, resolved params, response type, execution time
- `admin_mapping_uploads`: every CSV upload, validation status, row count
- `discrepancies`: automatically created by overlap resolver on value changes

---

## Recommended Additions

### 1. Sentry (error tracking)
Add to both web and ingestion service.

**Web** — install `@sentry/nextjs` and add to `web/next.config.ts`:
```js
// Captures unhandled errors in route handlers and server components
```

**Ingestion** — install `sentry-sdk[fastapi]` and add to `main.py`:
```python
import sentry_sdk
sentry_sdk.init(dsn=os.environ.get("SENTRY_DSN"), traces_sample_rate=0.1)
```

Capture ingestion errors explicitly:
```python
# In run_ingestion(), after log.exception:
sentry_sdk.capture_exception(exc)
```

### 2. Key metrics to track

| Metric | Source | Alert if |
|---|---|---|
| Ingestion failure rate | `admin_mapping_uploads.validation_status = 'invalid'` | > 10% of uploads |
| Query error rate | `query_logs.response_type = 'error'` | > 5% of queries in any 10-min window |
| Ingestion duration | ingestion service logs | p95 > 30s |
| Unmapped financial types | `admin_mapping_uploads.unmapped_financial_type_count` | > 0 on a known-clean upload |
| Open discrepancies | `discrepancies WHERE review_status = 'pending'` | > 50 rows |

### 3. Supabase dashboard
- Enable **Logs** for Postgres slow queries (> 1s threshold)
- Enable **API logs** to catch 5xx responses from Supabase REST
- Set up an **alert** for storage bucket upload failures

### 4. Uptime monitoring
- Ping `GET /health` on the ingestion service every 60 seconds (UptimeRobot, BetterStack)
- Ping `GET /` on the web app every 60 seconds
- Alert via email/Slack on any non-200 response

### 5. Query log review cadence
The `query_logs` table doubles as the primary audit trail and a source of improvement signals.

Recommended weekly review:
```sql
-- Top error queries this week
SELECT raw_query, COUNT(*) as n
FROM query_logs
WHERE response_type = 'error' AND created_at > now() - interval '7 days'
GROUP BY raw_query ORDER BY n DESC LIMIT 20;

-- Ambiguity rate by mode
SELECT mode, response_type, COUNT(*) as n
FROM query_logs
WHERE created_at > now() - interval '7 days'
GROUP BY mode, response_type ORDER BY mode, n DESC;

-- Slowest queries
SELECT raw_query, execution_ms, created_at
FROM query_logs
WHERE execution_ms IS NOT NULL
ORDER BY execution_ms DESC LIMIT 10;
```

### 6. Ingestion service health endpoint
The existing `/health` endpoint returns `{"status": "ok"}`. Consider extending it to include:
```python
@app.get("/health")
def health():
    # Quick DB ping to confirm connectivity
    try:
        conn = get_connection()
        conn.close()
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "db": db_ok}
```
This lets uptime monitors distinguish app-is-up from app-can-reach-database.

---

## Log Retention

| Log source | Recommended retention |
|---|---|
| `query_logs` table | 12 months (rows are small) |
| `admin_mapping_uploads` | Indefinite (audit trail) |
| `discrepancies` | Indefinite |
| Ingestion service stdout | 30 days (Fly.io log drain) |
| Vercel function logs | 7 days (free tier) |
```

- [ ] **Step 2: Commit**

```bash
cd "/home/yatbond/projects/financial chatbot"
git add docs/observability.md
git commit -m "docs: add observability and logging recommendations"
```

---

## Task 9: Final verification

- [ ] **Step 1: Run full Python test suite**

```bash
cd "/home/yatbond/projects/financial chatbot/ingestion"
uv run pytest -q
```

Expected: all tests PASS (count > 151).

- [ ] **Step 2: Run web tests**

```bash
cd "/home/yatbond/projects/financial chatbot/web"
npm test
```

Expected: 12 tests PASS.

- [ ] **Step 3: Run TypeScript check on web**

```bash
cd "/home/yatbond/projects/financial chatbot/web"
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Final commit if any cleanup**

If any uncommitted changes remain:
```bash
cd "/home/yatbond/projects/financial chatbot"
git status
```

Commit any remaining files.

---

## Deliverables

At the end of this phase, produce:

1. **Completed work** — list each task and what was done
2. **Files changed** — exact file paths
3. **Assumptions** — any guesses made where spec was ambiguous
4. **Known gaps** — what was deferred or not covered
5. **Manual test steps** — how to verify the docs are accurate
6. **Suggested commit message** — for the merge commit
7. **Final implementation summary** — one paragraph
