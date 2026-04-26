# Phase 13: Wire the Real Chat Resolver

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the mock TypeScript chat resolver with a real pipeline: the Python `QueryResolver` + `ShortcutEngine` runs inside the ingestion service and returns live financial data from Supabase.

**Architecture:** Add a `POST /query` endpoint to the FastAPI ingestion service. It builds `QueryResolver` from DB mapping tables, runs the query through `ShortcutEngine` backed by a new `PostgresDataProvider`, and returns a JSON payload that matches the existing `ChatResponse` TypeScript type verbatim. The web chat route looks up the project UUID from Supabase, then forwards the request to the ingestion service. The mock `resolver.ts` is deleted and replaced by an async HTTP client.

**Tech Stack:** Python 3.12 + FastAPI + psycopg2 (ingestion); Next.js 15 App Router + TypeScript (web); Supabase Postgres (`normalized_financial_rows`, `financial_type_map`, `heading_map`, `heading_aliases`).

**Baseline:** `uv run pytest -q` → 196 passed. `npm test` → 12 passed. Both must still pass after every task.

---

## File Structure

**Created:**
- `ingestion/src/postgres_data_provider.py` — `PostgresDataProvider(DataProvider)` backed by `normalized_financial_rows` via psycopg2
- `ingestion/src/resolver_service.py` — `build_resolver()`, `resolve_and_execute()`, and serializers that convert Python `ExecutionResult` → `ChatResponse` JSON
- `ingestion/tests/test_resolver_service.py` — full test suite for the serialization + pipeline layer

**Modified:**
- `ingestion/main.py` — add `QueryRequest` Pydantic model and `POST /query` endpoint
- `web/lib/chat/resolver.ts` — replace 674-line mock with a 40-line async HTTP client
- `web/app/api/projects/[projectId]/chat/route.ts` — look up project UUID from Supabase; make `resolveQuery` call `await`

---

## Task 1: PostgresDataProvider

**Files:**
- Create: `ingestion/src/postgres_data_provider.py`

- [ ] **Step 1: Write the file**

Create `ingestion/src/postgres_data_provider.py`:

```python
"""PostgresDataProvider — DataProvider backed by normalized_financial_rows via psycopg2."""

from __future__ import annotations

import psycopg2.extras

from .shortcut_engine import DataProvider, FinancialRow


class PostgresDataProvider(DataProvider):
    """DataProvider that queries normalized_financial_rows via psycopg2."""

    def __init__(self, conn) -> None:
        self._conn = conn

    def fetch_rows(
        self,
        project_id: str,
        sheet_name: str,
        *,
        financial_type: str | None = None,
        item_code: str | None = None,
        data_type: str | None = None,
        report_month: int | None = None,
        report_year: int | None = None,
        item_code_prefix: str | None = None,
        is_active: bool = True,
    ) -> list[FinancialRow]:
        clauses = ["project_id = %s", "sheet_name = %s", "is_active = %s"]
        params: list = [project_id, sheet_name, is_active]

        if financial_type is not None:
            clauses.append("financial_type = %s")
            params.append(financial_type)
        if item_code is not None:
            clauses.append("item_code = %s")
            params.append(item_code)
        if data_type is not None:
            clauses.append("data_type = %s")
            params.append(data_type)
        if report_month is not None:
            clauses.append("report_month = %s")
            params.append(report_month)
        if report_year is not None:
            clauses.append("report_year = %s")
            params.append(report_year)
        if item_code_prefix is not None:
            clauses.append("(item_code = %s OR item_code LIKE %s)")
            params.extend([item_code_prefix, item_code_prefix + ".%"])

        sql = (
            "SELECT project_id, sheet_name, report_month, report_year, "
            "financial_type, item_code, data_type, friendly_name, category, tier, value "
            "FROM normalized_financial_rows WHERE " + " AND ".join(clauses)
        )
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [_to_row(dict(r)) for r in cur.fetchall()]

    def fetch_rows_for_periods(
        self,
        project_id: str,
        sheet_name: str,
        financial_type: str | None,
        item_code: str | None,
        periods: list[tuple[int, int]],
        is_active: bool = True,
    ) -> list[FinancialRow]:
        if not periods:
            return []
        period_clause = " OR ".join(["(report_month = %s AND report_year = %s)"] * len(periods))
        clauses = [
            "project_id = %s", "sheet_name = %s", "is_active = %s",
            f"({period_clause})",
        ]
        params: list = [project_id, sheet_name, is_active]
        for m, y in periods:
            params.extend([m, y])

        if financial_type is not None:
            clauses.append("financial_type = %s")
            params.append(financial_type)
        if item_code is not None:
            clauses.append("item_code = %s")
            params.append(item_code)

        sql = (
            "SELECT project_id, sheet_name, report_month, report_year, "
            "financial_type, item_code, data_type, friendly_name, category, tier, value "
            "FROM normalized_financial_rows WHERE " + " AND ".join(clauses)
        )
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [_to_row(dict(r)) for r in cur.fetchall()]

    def get_latest_period(
        self,
        project_id: str,
        sheet_name: str,
        financial_type: str | None = None,
    ) -> tuple[int, int] | None:
        sql = (
            "SELECT report_month, report_year FROM normalized_financial_rows "
            "WHERE project_id = %s AND sheet_name = %s AND is_active = TRUE"
        )
        params: list = [project_id, sheet_name]
        if financial_type is not None:
            sql += " AND financial_type = %s"
            params.append(financial_type)
        sql += " ORDER BY report_year DESC, report_month DESC LIMIT 1"

        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return (row[0], row[1]) if row else None


def _to_row(r: dict) -> FinancialRow:
    return FinancialRow(
        project_id=r["project_id"],
        sheet_name=r["sheet_name"],
        report_month=r["report_month"],
        report_year=r["report_year"],
        financial_type=r.get("financial_type"),
        item_code=r.get("item_code"),
        data_type=r.get("data_type"),
        friendly_name=r.get("friendly_name"),
        category=r.get("category"),
        tier=r.get("tier"),
        value=r.get("value"),
    )
```

- [ ] **Step 2: Verify it imports cleanly**

```bash
cd "/home/yatbond/projects/financial chatbot/ingestion"
uv run python -c "from src.postgres_data_provider import PostgresDataProvider; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Run full test suite (no regressions)**

```bash
cd "/home/yatbond/projects/financial chatbot/ingestion"
uv run pytest -q
```

Expected: 196 passed.

- [ ] **Step 4: Commit**

```bash
cd "/home/yatbond/projects/financial chatbot"
git add ingestion/src/postgres_data_provider.py
git commit -m "feat(ingestion): add PostgresDataProvider backed by normalized_financial_rows"
```

---

## Task 2: Resolver service — serialization + pipeline

**Files:**
- Create: `ingestion/src/resolver_service.py`

- [ ] **Step 1: Write the file**

Create `ingestion/src/resolver_service.py`:

```python
"""
Resolver service — wires QueryResolver + ShortcutEngine into a single
resolve_and_execute() that returns a ChatResponse-compatible dict.
"""

from __future__ import annotations

import psycopg2.extras

from .query_resolver import (
    AmbiguityResult,
    ConversationContext,
    QueryResolver,
    ResolutionResult,
)
from .shortcut_engine import (
    DataProvider,
    NoDataResult,
    ShortcutEngine,
    ShortcutHelpResult,
    TableResult,
    TypeListResult,
    ValueResult,
)


def build_resolver(conn) -> tuple[QueryResolver, dict[str, dict]]:
    """
    Load QueryResolver and heading_map from the active DB mapping tables.
    Returns (resolver, heading_map).
    heading_map shape: {item_code: {data_type, friendly_name, category, tier}}
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT raw_financial_type, clean_financial_type, acronyms "
            "FROM financial_type_map WHERE is_active = true"
        )
        ft_rows = [
            {
                "Clean_Financial_Type": r["clean_financial_type"],
                "Acronyms": "|".join(r["acronyms"] or []),
            }
            for r in cur.fetchall()
        ]

        cur.execute(
            """
            SELECT hm.item_code, hm.data_type, hm.friendly_name, hm.category, hm.tier,
                   COALESCE(string_agg(ha.alias, '|'), '') AS acronyms
              FROM heading_map hm
              LEFT JOIN heading_aliases ha ON ha.heading_map_id = hm.id
             WHERE hm.is_active = true
             GROUP BY hm.id, hm.item_code, hm.data_type,
                      hm.friendly_name, hm.category, hm.tier
            """
        )
        heading_rows = [
            {
                "Item_Code": r["item_code"],
                "Data_Type": r["data_type"],
                "Friendly_Name": r["friendly_name"],
                "Category": r["category"] or "",
                "Tier": r["tier"] or 0,
                "Acronyms": r["acronyms"],
            }
            for r in cur.fetchall()
        ]

    heading_map = {
        r["Item_Code"]: {
            "data_type": r["Data_Type"],
            "friendly_name": r["Friendly_Name"],
            "category": r["Category"],
            "tier": r["Tier"],
        }
        for r in heading_rows
        if r["Item_Code"]
    }

    return QueryResolver.from_csv_dicts(ft_rows, heading_rows), heading_map


def _context_from_dict(d: dict) -> ConversationContext:
    return ConversationContext(
        project_id=d.get("project_id"),
        project_code=d.get("project_code"),
        project_name=d.get("project_name"),
        financial_type=d.get("financial_type"),
        data_type=d.get("data_type"),
        sheet_name=d.get("sheet_name"),
        month=d.get("month"),
        year=d.get("year"),
        report_month=d.get("report_month"),
        report_year=d.get("report_year"),
        last_shortcut=d.get("last_shortcut"),
    )


def _resolved_to_params(r) -> dict:
    """Extract key fields from ResolvedQuery as a flat dict for AmbiguityOption params."""
    return {
        "financial_type": r.financial_type,
        "data_type": r.data_type,
        "item_code": r.item_code,
        "sheet_name": r.sheet_name,
        "shortcut": r.shortcut,
        "month": r.month,
        "year": r.year,
        "num_months": r.num_months,
    }


def _ambiguity_to_response(result: AmbiguityResult) -> dict:
    """Convert AmbiguityResult → AmbiguityResponse dict."""
    options = [
        {"label": interp.label, "params": _resolved_to_params(interp.resolved)}
        for interp in result.interpretations
    ]
    partial = result.partial
    interpretation: dict = {}
    if partial:
        interpretation = {
            "shortcut": partial.shortcut,
            "financial_type": partial.financial_type,
            "data_type": partial.data_type,
            "sheet_name": partial.sheet_name,
        }
    return {
        "type": "ambiguity",
        "interpretation": interpretation,
        "prompt": result.reason or "Please clarify your query.",
        "options": options,
    }


def _exec_to_response(resolved, exec_result) -> dict:
    """Convert ExecutionResult + ResolvedQuery → ChatResponse dict."""
    if isinstance(exec_result, ValueResult):
        interp = {
            "financial_type": exec_result.financial_type or resolved.financial_type,
            "data_type": exec_result.data_type or resolved.data_type,
            "sheet_name": resolved.sheet_name,
            "period": exec_result.period,
            "shortcut": resolved.shortcut,
        }
        return {
            "type": "result",
            "interpretation": interp,
            "columns": ["Financial Type", "Data Type", "Period", "Value (HK$)"],
            "rows": [{
                "Financial Type": exec_result.financial_type,
                "Data Type": exec_result.data_type,
                "Period": exec_result.period,
                "Value (HK$)": exec_result.value,
            }],
            "summary": f"{exec_result.label} — {exec_result.period}",
            "warning": exec_result.warnings[0] if exec_result.warnings else None,
            "context_update": {
                "financial_type": exec_result.financial_type or None,
                "data_type": exec_result.data_type or None,
                "sheet_name": resolved.sheet_name,
            },
        }

    if isinstance(exec_result, TableResult):
        interp = {
            "shortcut": exec_result.shortcut or resolved.shortcut,
            "financial_type": resolved.financial_type,
            "data_type": resolved.data_type,
            "sheet_name": resolved.sheet_name,
        }
        return {
            "type": "result",
            "interpretation": interp,
            "columns": exec_result.columns,
            "rows": exec_result.rows,
            "summary": exec_result.title or None,
            "warning": exec_result.warnings[0] if exec_result.warnings else None,
            "context_update": {
                "last_shortcut": exec_result.shortcut or resolved.shortcut,
                "financial_type": resolved.financial_type,
                "data_type": resolved.data_type,
                "sheet_name": resolved.sheet_name,
            },
        }

    if isinstance(exec_result, NoDataResult):
        return {
            "type": "missing",
            "interpretation": {
                "financial_type": resolved.financial_type,
                "data_type": resolved.data_type,
                "sheet_name": resolved.sheet_name,
            },
            "message": exec_result.reason,
        }

    if isinstance(exec_result, ShortcutHelpResult):
        lines: list[str] = []
        for item in exec_result.items:
            lines.append(f"{item['name']} — {item['description']}")
            if item.get("example"):
                lines.append(f"  Example: {item['example']}")
        return {
            "type": "info",
            "title": "Supported Shortcuts",
            "content": "\n".join(lines),
        }

    if isinstance(exec_result, TypeListResult):
        lines = []
        for item in exec_result.items:
            line = f"{item['financial_type']} ({item['sheet_name']})"
            if item.get("aliases"):
                line += f" — aliases: {item['aliases']}"
            lines.append(line)
        return {
            "type": "info",
            "title": "Available Financial Types & Sheets",
            "content": "\n".join(lines),
        }

    return {"type": "error", "message": "Unknown result type from execution engine."}


def resolve_and_execute(
    query: str,
    project_id: str,
    context_dict: dict,
    mode: str = "standard",
    selected_option_index: int | None = None,
    prior_options: list[dict] | None = None,
    *,
    resolver: QueryResolver,
    provider: DataProvider,
    heading_map: dict[str, dict],
) -> dict:
    """
    Full pipeline: resolve query → execute against DataProvider → return ChatResponse dict.

    When selected_option_index + prior_options are provided (user picked an ambiguity option),
    the selected option's params are merged into context before re-running the resolver.
    """
    ctx = _context_from_dict(context_dict)
    ctx.project_id = project_id

    if selected_option_index is not None and prior_options:
        if 0 <= selected_option_index < len(prior_options):
            params = prior_options[selected_option_index].get("params", {})
            ctx.financial_type = params.get("financial_type") or ctx.financial_type
            ctx.data_type = params.get("data_type") or ctx.data_type
            ctx.sheet_name = params.get("sheet_name") or ctx.sheet_name
            if params.get("month"):
                ctx.month = params["month"]
            if params.get("year"):
                ctx.year = params["year"]

    result = resolver.resolve(query, ctx)

    if isinstance(result, AmbiguityResult):
        return _ambiguity_to_response(result)

    resolved = result.resolved
    engine = ShortcutEngine(provider, heading_map)
    exec_result = engine.execute(resolved)
    return _exec_to_response(resolved, exec_result)
```

- [ ] **Step 2: Verify it imports cleanly**

```bash
cd "/home/yatbond/projects/financial chatbot/ingestion"
uv run python -c "from src.resolver_service import build_resolver, resolve_and_execute; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Run full test suite (no regressions)**

```bash
cd "/home/yatbond/projects/financial chatbot/ingestion"
uv run pytest -q
```

Expected: 196 passed.

- [ ] **Step 4: Commit**

```bash
cd "/home/yatbond/projects/financial chatbot"
git add ingestion/src/resolver_service.py
git commit -m "feat(ingestion): add resolver_service — build_resolver, resolve_and_execute, serializers"
```

---

## Task 3: /query endpoint in main.py

**Files:**
- Modify: `ingestion/main.py`

- [ ] **Step 1: Read current main.py**

```bash
cat -n "/home/yatbond/projects/financial chatbot/ingestion/main.py"
```

The current file is 45 lines. You will add imports, two new Pydantic models, and one new route.

- [ ] **Step 2: Replace main.py**

Write the complete updated `ingestion/main.py`:

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
from src.db import get_connection
from src.ingestion import run_ingestion
from src.postgres_data_provider import PostgresDataProvider
from src.resolver_service import build_resolver, resolve_and_execute

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

app = FastAPI(title="FinLens Ingestion Service")

_UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE,
)


# ── Ingest endpoint ───────────────────────────────────────────────────────────

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


# ── Query endpoint ────────────────────────────────────────────────────────────

class ContextPayload(BaseModel):
    project_id: str | None = None
    project_code: str | None = None
    project_name: str | None = None
    financial_type: str | None = None
    data_type: str | None = None
    sheet_name: str | None = None
    month: int | None = None
    year: int | None = None
    report_month: int | None = None
    report_year: int | None = None
    last_shortcut: str | None = None


class AmbiguityOptionPayload(BaseModel):
    label: str
    params: dict = {}


class QueryRequest(BaseModel):
    query: str
    project_id: str
    context: ContextPayload = ContextPayload()
    mode: str = "standard"
    selected_option_index: int | None = None
    prior_options: list[AmbiguityOptionPayload] | None = None


@app.post("/query")
def query_endpoint(req: QueryRequest):
    conn = get_connection()
    try:
        resolver, heading_map = build_resolver(conn)
        provider = PostgresDataProvider(conn)
        result = resolve_and_execute(
            query=req.query,
            project_id=req.project_id,
            context_dict=req.context.model_dump(),
            mode=req.mode,
            selected_option_index=req.selected_option_index,
            prior_options=(
                [o.model_dump() for o in req.prior_options]
                if req.prior_options else None
            ),
            resolver=resolver,
            provider=provider,
            heading_map=heading_map,
        )
        return JSONResponse(result)
    except Exception as exc:
        log.exception("Query resolution failed for project=%s query=%r", req.project_id, req.query)
        return JSONResponse({"type": "error", "message": "Query resolution failed."}, status_code=500)
    finally:
        conn.close()


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=INGESTION_PORT, reload=False)
```

- [ ] **Step 3: Run full test suite (no regressions)**

```bash
cd "/home/yatbond/projects/financial chatbot/ingestion"
uv run pytest -q
```

Expected: 196 passed.

- [ ] **Step 4: Commit**

```bash
cd "/home/yatbond/projects/financial chatbot"
git add ingestion/main.py
git commit -m "feat(ingestion): add POST /query endpoint backed by real QueryResolver + ShortcutEngine"
```

---

## Task 4: Tests for resolver_service

**Files:**
- Create: `ingestion/tests/test_resolver_service.py`

- [ ] **Step 1: Write the test file**

Create `ingestion/tests/test_resolver_service.py`:

```python
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
Accrual\n(Before Retention) as at,Accrual,accrual|accrued
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
        rows = [_make_row("3", "Projection", 12_450_000)]
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
        rows = [_make_row("3", "Projection", 5_000_000)]
        resp = resolve_and_execute(
            query="gp",
            project_id=PROJECT,
            context_dict={"report_month": 2, "report_year": 2026},
            selected_option_index=0,
            prior_options=[{
                "label": "Projection (Financial Status)",
                "params": {"financial_type": "Projection", "sheet_name": "Financial Status"},
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
```

- [ ] **Step 2: Run the new tests**

```bash
cd "/home/yatbond/projects/financial chatbot/ingestion"
uv run pytest tests/test_resolver_service.py -v 2>&1 | tail -40
```

Expected: all tests PASS.

- [ ] **Step 3: Run full test suite**

```bash
cd "/home/yatbond/projects/financial chatbot/ingestion"
uv run pytest -q
```

Expected: all tests pass (count > 196).

- [ ] **Step 4: Commit**

```bash
cd "/home/yatbond/projects/financial chatbot"
git add ingestion/tests/test_resolver_service.py
git commit -m "test(resolver_service): add full test suite for serializers and resolve_and_execute()"
```

---

## Task 5: Replace web resolver.ts with HTTP client

**Files:**
- Replace: `web/lib/chat/resolver.ts`

The current file is 674 lines of mock logic. Replace it entirely.

- [ ] **Step 1: Read the current resolver.ts to confirm it has the right export signature**

```bash
head -20 "/home/yatbond/projects/financial chatbot/web/lib/chat/resolver.ts"
```

The export to replace is: `export function resolveQuery(req: ChatRequest): ChatResponse`

- [ ] **Step 2: Write the replacement resolver.ts**

Write the complete new `web/lib/chat/resolver.ts`:

```typescript
// Real query resolver — delegates to the Python ingestion service /query endpoint.
// Replaces the Phase 9 mock. Requires INGESTION_SERVICE_URL env var.

import type { ChatRequest, ChatResponse } from './types'

export async function resolveQuery(
  req: ChatRequest,
  projectUuid: string,
): Promise<ChatResponse> {
  const ingestionUrl = process.env.INGESTION_SERVICE_URL
  if (!ingestionUrl) {
    return {
      type: 'error',
      message: 'Query service is not configured. Set INGESTION_SERVICE_URL.',
    }
  }

  const body = {
    query: req.query,
    project_id: projectUuid,
    context: req.context ?? {},
    mode: req.mode ?? 'standard',
    selected_option_index: req.selected_option_index ?? null,
    prior_options: req.prior_options ?? null,
  }

  let res: Response
  try {
    res = await fetch(`${ingestionUrl}/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    return { type: 'error', message: 'Could not reach query service.' }
  }

  if (!res.ok) {
    return { type: 'error', message: `Query service error (HTTP ${res.status}).` }
  }

  return res.json() as Promise<ChatResponse>
}
```

- [ ] **Step 3: Run TypeScript check**

```bash
cd "/home/yatbond/projects/financial chatbot/web"
npx tsc --noEmit 2>&1 | head -30
```

Expected: errors related to `route.ts` calling `resolveQuery` synchronously — **this is expected** and will be fixed in Task 6. Any errors NOT in `route.ts` are real problems to fix before continuing.

- [ ] **Step 4: Run web tests**

```bash
cd "/home/yatbond/projects/financial chatbot/web"
npm test
```

Expected: 12 passed. (Web tests do not import from resolver.ts directly.)

- [ ] **Step 5: Commit**

```bash
cd "/home/yatbond/projects/financial chatbot"
git add web/lib/chat/resolver.ts
git commit -m "feat(web): replace mock resolver with async HTTP client calling /query endpoint"
```

---

## Task 6: Update chat route — async resolver + project UUID lookup

**Files:**
- Modify: `web/app/api/projects/[projectId]/chat/route.ts`

The route must now: (1) look up the project UUID from Supabase, (2) call `await resolveQuery(body, projectUuid)`.

- [ ] **Step 1: Read the current route.ts**

```bash
cat -n "/home/yatbond/projects/financial chatbot/web/app/api/projects/[projectId]/chat/route.ts"
```

- [ ] **Step 2: Write the updated route.ts**

Write the complete new `web/app/api/projects/[projectId]/chat/route.ts`:

```typescript
import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'
import { resolveQuery } from '@/lib/chat/resolver'
import { createServerSupabase } from '@/lib/supabase/server'
import type { ChatRequest, ChatResponse } from '@/lib/chat/types'
import type { QueryLogInsert, ResponseType } from '@/lib/types/database'

function toResponseType(res: ChatResponse): ResponseType | null {
  if (res.type === 'ambiguity') return 'ambiguity'
  if (res.type === 'missing') return 'missing'
  if (res.type === 'error') return 'error'
  if (res.type === 'info') return null
  if (res.type === 'result') {
    const shortcut = res.interpretation.shortcut
    if (shortcut === 'Trend') return 'trend'
    if (shortcut === 'Compare') return 'compare'
    if (shortcut === 'Total') return 'total'
    if (shortcut === 'Detail') return 'detail'
    if (shortcut === 'Risk') return 'risk'
    if (shortcut === 'Cash Flow Shortcut') return 'cash_flow'
    if (shortcut === 'List') return 'list'
    if (shortcut === 'Analyze') return 'table'
    return res.rows.length > 1 ? 'table' : 'value'
  }
  return null
}

async function insertQueryLog(
  projectId: string,
  body: ChatRequest,
  response: ChatResponse,
  executionMs: number,
  userId: string,
): Promise<void> {
  const supabase = createServerSupabase()
  const interp: Partial<{
    sheet_name: string
    financial_type: string
    data_type: string
    shortcut: string
  }> = (response.type === 'result' || response.type === 'ambiguity' || response.type === 'missing')
    ? response.interpretation
    : {}

  const log: QueryLogInsert = {
    project_id: projectId,
    user_id: userId,
    raw_query: body.query,
    resolved_sheet_name: interp.sheet_name ?? null,
    resolved_financial_type: interp.financial_type ?? null,
    resolved_data_type: interp.data_type ?? null,
    resolved_item_code: null,
    resolved_month: null,
    resolved_year: null,
    resolved_shortcut: interp.shortcut ?? null,
    interpretation_options: response.type === 'ambiguity'
      ? response.options.map(o => ({ label: o.label, params: o.params as Record<string, string | number | undefined> }))
      : null,
    selected_option_index: body.selected_option_index ?? null,
    was_ambiguous: response.type === 'ambiguity',
    mode: body.mode ?? 'standard',
    response_type: toResponseType(response),
    execution_ms: executionMs,
  }

  await supabase.from('query_logs').insert(log)
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ projectId: string }> }
) {
  const { projectId } = await params

  let body: ChatRequest
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ type: 'error', message: 'Invalid request body.' }, { status: 400 })
  }

  if (!body.query?.trim()) {
    return NextResponse.json({ type: 'error', message: 'Query is required.' }, { status: 400 })
  }

  if (!body.context) body.context = {}
  if (!body.context.project_code) body.context.project_code = projectId

  // Look up real project UUID — needed by the ingestion service for DB queries
  let projectUuid: string
  try {
    const supabase = createServerSupabase()
    const { data: project } = await supabase
      .from('projects')
      .select('id')
      .eq('project_code', projectId)
      .single()
    if (!project) {
      return NextResponse.json({ type: 'error', message: 'Project not found.' }, { status: 404 })
    }
    projectUuid = project.id
  } catch {
    return NextResponse.json(
      { type: 'error', message: 'Database is not configured.' },
      { status: 500 }
    )
  }

  const startMs = Date.now()

  let response: ChatResponse
  try {
    response = await resolveQuery(body, projectUuid)
  } catch (err) {
    console.error('[chat/route] resolver error', err)
    return NextResponse.json({ type: 'error', message: 'Query resolution failed.' }, { status: 500 })
  }

  const executionMs = Date.now() - startMs

  // Fire-and-forget — never let logging break the response
  try {
    const { userId } = await auth()
    await insertQueryLog(projectId, body, response, executionMs, userId ?? 'anon')
  } catch (err) {
    console.warn('[chat/route] query_log insert failed (non-fatal)', err)
  }

  return NextResponse.json(response)
}
```

Note: `toResponseType` now uses `'Trend'` (capital T) to match the Python engine's shortcut names. The mock used lowercase `'trend'`; the real Python engine returns `'Trend'`.

- [ ] **Step 3: Run TypeScript check — must be clean**

```bash
cd "/home/yatbond/projects/financial chatbot/web"
npx tsc --noEmit 2>&1
```

Expected: no output (zero errors).

- [ ] **Step 4: Run web tests**

```bash
cd "/home/yatbond/projects/financial chatbot/web"
npm test
```

Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
cd "/home/yatbond/projects/financial chatbot"
git add web/app/api/projects/[projectId]/chat/route.ts
git commit -m "feat(web): wire chat route to real resolver — UUID lookup + async resolveQuery"
```

---

## Task 7: Final verification

- [ ] **Step 1: Run full Python test suite**

```bash
cd "/home/yatbond/projects/financial chatbot/ingestion"
uv run pytest -q
```

Expected: all tests PASS (count > 196).

- [ ] **Step 2: Run web tests and TypeScript check**

```bash
cd "/home/yatbond/projects/financial chatbot/web"
npm test && npx tsc --noEmit
```

Expected: 12 passed, 0 TypeScript errors.

- [ ] **Step 3: Manual smoke test checklist (requires running services)**

If `INGESTION_SERVICE_URL` is configured and the ingestion service is running:

```bash
# Start ingestion service
cd "/home/yatbond/projects/financial chatbot/ingestion"
uv run uvicorn main:app --port 8000

# In another terminal — test /query directly
curl -s -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "shortcut", "project_id": "any-uuid-00000000-0000-0000-0000-000000000000"}' | python3 -m json.tool
```

Expected: `{"type": "info", "title": "Supported Shortcuts", "content": "..."}`

```bash
curl -s -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "list", "project_id": "any-uuid-00000000-0000-0000-0000-000000000000"}' | python3 -m json.tool
```

Expected: `{"type": "result", "columns": [...], "rows": [...]}`

- [ ] **Step 4: Final commit (if any cleanup needed)**

If no cleanup needed, this step is a no-op. Otherwise:

```bash
cd "/home/yatbond/projects/financial chatbot"
git add -p  # stage only relevant changes
git commit -m "fix: <describe cleanup>"
```

---

## Self-Review

**Spec coverage:**
- PostgresDataProvider implements all 3 DataProvider methods ✓
- build_resolver loads financial_type_map + heading_aliases ✓
- resolve_and_execute handles ambiguity, value, table, no-data, info ✓
- /query endpoint validates nothing beyond Pydantic schema (project_id must be str; empty string will return DB error gracefully) ✓
- resolveQuery in web is async + calls INGESTION_SERVICE_URL/query ✓
- route.ts looks up UUID before calling resolver ✓
- shortcut name capitalisation fixed (Trend not trend) ✓
- Ambiguity option selection merges params into context before re-resolving ✓

**Placeholder scan:** None found.

**Type consistency:**
- `resolveQuery(req: ChatRequest, projectUuid: string): Promise<ChatResponse>` used in both resolver.ts (definition) and route.ts (call) ✓
- `resolve_and_execute(..., *, resolver, provider, heading_map)` used in resolver_service.py (definition), main.py (call), and test_resolver_service.py (calls) ✓
- `build_resolver(conn) → tuple[QueryResolver, dict[str, dict]]` used in resolver_service.py (definition) and main.py (unpacking) ✓
