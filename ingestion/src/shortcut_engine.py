"""
Shortcut Execution Engine — Phase 8

Given a resolved ResolvedQuery from query_resolver.py, executes the appropriate
query against normalized_financial_rows and returns a structured result payload.

Entry point:
    engine = ShortcutEngine(provider, heading_map)
    result = engine.execute(resolved)  # → ExecutionResult
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

from .query_resolver import (
    FieldSet,
    MONTH_LABELS,
    MONTHLY_FINANCIAL_TYPES,
    SNAPSHOT_SHEET,
    ResolvedQuery,
)

log = logging.getLogger(__name__)


# ── Constants ─────────────────────────────────────────────────────────────────

# Risk shortcut item codes (PRD §13.10)
_RISK_INCOME_CODES = ["1.2.1", "1.7", "1.8", "1.12.1"]
_RISK_COST_CODES = ["2.2.15", "2.4.4", "2.4.7", "2.7", "2.8", "2.14"]
_RISK_FT_COLUMNS = ["WIP", "Committed Cost", "Cash Flow"]

# Analyze rules: (projection_ft, comparison_ft, item_category, exception_condition)
# exception_condition: "proj_less_b" for income (bad if projection falls short of comparison)
#                      "proj_greater_b" for cost (bad if projection exceeds comparison)
_ANALYZE_RULES: list[tuple[str, str, str, str]] = [
    ("Projection", "WIP",            "Income", "proj_less_b"),
    ("Projection", "Business Plan",  "Income", "proj_less_b"),
    ("Projection", "Accrual",        "Cost",   "proj_greater_b"),
    ("Projection", "Committed Cost", "Cost",   "proj_greater_b"),
    ("Projection", "Cash Flow",      "Cost",   "proj_greater_b"),
]

# Cash Flow shortcut item codes (PRD §13.11)
_CASH_FLOW_ITEMS: list[tuple[str, str]] = [
    ("3", "Gross Profit"),
    ("5", "Gross Profit (after recon & overhead)"),
]

_SHORTCUT_DESCRIPTIONS: list[dict] = [
    {
        "name": "Shortcut",
        "description": "List all supported shortcuts and how to use them.",
        "example": "shortcut",
    },
    {
        "name": "Analyze",
        "description": (
            "Show exception items: income where Projection < WIP or Business Plan; "
            "cost where Projection > Accrual, Committed Cost, or Cash Flow."
        ),
        "example": "analyze",
    },
    {
        "name": "Compare",
        "description": "Compare two values side by side (Value A, Value B, Difference).",
        "example": "compare projected gp vs wip gp",
    },
    {
        "name": "Trend",
        "description": "Show historical monthly data for the last N months (default 6).",
        "example": "trend gp 8",
    },
    {
        "name": "List",
        "description": "List tier 1 and tier 2 items. Use 'list 2.2' to drill into a subtree.",
        "example": "list 2.2",
    },
    {
        "name": "Total",
        "description": "Show total value and immediate item breakdown.",
        "example": "total cost projected",
    },
    {
        "name": "Detail",
        "description": "Show the full hierarchy of all child items.",
        "example": "detail cash flow prelim",
    },
    {
        "name": "Risk",
        "description": (
            "Show risk-sensitive items across WIP, Committed Cost, and Cash Flow "
            "on Financial Status."
        ),
        "example": "risk",
    },
    {
        "name": "Cash Flow",
        "description": "Show last 12 months of Gross Profit items from the Cash Flow sheet.",
        "example": "cash flow",
    },
    {
        "name": "Type",
        "description": "List all available financial types and which sheet they belong to.",
        "example": "type",
    },
]

_FINANCIAL_TYPE_REFS: list[dict] = [
    {"financial_type": "Financial Status",  "sheet_name": "Financial Status",  "aliases": "fs"},
    {"financial_type": "Projection",        "sheet_name": "Projection (monthly)",       "aliases": "projected, projection"},
    {"financial_type": "Committed Cost",    "sheet_name": "Committed Cost (monthly)",   "aliases": "committed"},
    {"financial_type": "Accrual",           "sheet_name": "Accrual (monthly)",           "aliases": "accrual, accrued"},
    {"financial_type": "Cash Flow",         "sheet_name": "Cash Flow (monthly)",         "aliases": "cf, cashflow, cash flow"},
    {"financial_type": "WIP",               "sheet_name": "Financial Status",            "aliases": "wip, audit"},
    {"financial_type": "Business Plan",     "sheet_name": "Financial Status",            "aliases": "bp"},
    {"financial_type": "Latest Budget",     "sheet_name": "Financial Status",            "aliases": "budget, revision, rev"},
    {"financial_type": "1st Working Budget","sheet_name": "Financial Status",            "aliases": "1wb, first working"},
    {"financial_type": "Budget Tender",     "sheet_name": "Financial Status",            "aliases": "tender"},
    {"financial_type": "General",           "sheet_name": "Financial Status",            "aliases": "general"},
]


# ── Domain row ────────────────────────────────────────────────────────────────

@dataclass
class FinancialRow:
    """One row from normalized_financial_rows."""
    project_id: str
    sheet_name: str
    report_month: int
    report_year: int
    financial_type: str | None
    item_code: str | None
    data_type: str | None
    friendly_name: str | None
    category: str | None
    tier: int | None
    value: float | None


# ── Result payload schemas ────────────────────────────────────────────────────

@dataclass
class ValueResult:
    """Single-value lookup — no shortcut or direct retrieval."""
    result_type: str = field(default="value", init=False)
    label: str = ""
    value: float | None = None
    project: str = ""
    period: str = ""
    financial_type: str = ""
    data_type: str = ""
    item_code: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class TableResult:
    """Tabular result for Compare, Trend, List, Total, Detail, Analyze, Risk, Cash Flow."""
    result_type: str = field(default="table", init=False)
    shortcut: str = ""
    title: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    footer: dict | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class NoDataResult:
    """No matching rows found."""
    result_type: str = field(default="no_data", init=False)
    reason: str = "No matching data found."
    warnings: list[str] = field(default_factory=list)


@dataclass
class ShortcutHelpResult:
    """Static list of all supported shortcuts."""
    result_type: str = field(default="shortcut_help", init=False)
    items: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class TypeListResult:
    """List of all financial types and their sheets."""
    result_type: str = field(default="type_list", init=False)
    items: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


ExecutionResult = ValueResult | TableResult | NoDataResult | ShortcutHelpResult | TypeListResult


# ── Data provider interface ───────────────────────────────────────────────────

class DataProvider(ABC):
    """Abstract interface over normalized_financial_rows."""

    @abstractmethod
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
        """Return rows matching all provided filters."""

    @abstractmethod
    def fetch_rows_for_periods(
        self,
        project_id: str,
        sheet_name: str,
        financial_type: str | None,
        item_code: str | None,
        periods: list[tuple[int, int]],
        is_active: bool = True,
    ) -> list[FinancialRow]:
        """Return rows matching the given list of (month, year) periods."""

    @abstractmethod
    def get_latest_period(
        self,
        project_id: str,
        sheet_name: str,
        financial_type: str | None = None,
    ) -> tuple[int, int] | None:
        """Return the most recent (report_month, report_year) for this project/sheet/ft."""


class InMemoryDataProvider(DataProvider):
    """
    Test double for DataProvider — filters a list of FinancialRow fixtures in-memory.
    Pass `rows` at construction; all filter methods operate purely in Python.
    """

    def __init__(self, rows: list[FinancialRow]) -> None:
        self._rows = rows

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
        result = []
        for r in self._rows:
            if r.project_id != project_id:
                continue
            if r.sheet_name != sheet_name:
                continue
            if financial_type is not None and r.financial_type != financial_type:
                continue
            if item_code is not None and r.item_code != item_code:
                continue
            if data_type is not None and r.data_type != data_type:
                continue
            if report_month is not None and r.report_month != report_month:
                continue
            if report_year is not None and r.report_year != report_year:
                continue
            if item_code_prefix is not None:
                if r.item_code is None:
                    continue
                if not (
                    r.item_code == item_code_prefix
                    or r.item_code.startswith(item_code_prefix + ".")
                ):
                    continue
            result.append(r)
        return result

    def fetch_rows_for_periods(
        self,
        project_id: str,
        sheet_name: str,
        financial_type: str | None,
        item_code: str | None,
        periods: list[tuple[int, int]],
        is_active: bool = True,
    ) -> list[FinancialRow]:
        period_set = set(periods)
        result = []
        for r in self._rows:
            if r.project_id != project_id:
                continue
            if r.sheet_name != sheet_name:
                continue
            if financial_type is not None and r.financial_type != financial_type:
                continue
            if item_code is not None and r.item_code != item_code:
                continue
            if (r.report_month, r.report_year) not in period_set:
                continue
            result.append(r)
        return result

    def get_latest_period(
        self,
        project_id: str,
        sheet_name: str,
        financial_type: str | None = None,
    ) -> tuple[int, int] | None:
        candidates = [
            (r.report_month, r.report_year)
            for r in self._rows
            if r.project_id == project_id
            and r.sheet_name == sheet_name
            and (financial_type is None or r.financial_type == financial_type)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda p: (p[1], p[0]))


class PostgresDataProvider(DataProvider):
    """Live implementation using a psycopg2 connection."""

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
        import psycopg2.extras  # type: ignore

        conditions = ["project_id = %s", "sheet_name = %s"]
        params: list = [project_id, sheet_name]

        if is_active:
            conditions.append("is_active = TRUE")
        if financial_type is not None:
            conditions.append("financial_type = %s")
            params.append(financial_type)
        if item_code is not None:
            conditions.append("item_code = %s")
            params.append(item_code)
        if data_type is not None:
            conditions.append("data_type = %s")
            params.append(data_type)
        if report_month is not None:
            conditions.append("report_month = %s")
            params.append(report_month)
        if report_year is not None:
            conditions.append("report_year = %s")
            params.append(report_year)
        if item_code_prefix is not None:
            conditions.append("(item_code = %s OR item_code LIKE %s)")
            params.extend([item_code_prefix, item_code_prefix + ".%"])

        sql = (
            "SELECT project_id, sheet_name, report_month, report_year, "
            "financial_type, item_code, data_type, friendly_name, category, tier, value "
            "FROM normalized_financial_rows WHERE "
            + " AND ".join(conditions)
            + " ORDER BY item_code NULLS LAST, financial_type"
        )
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [_pg_row_to_financial_row(dict(r)) for r in cur.fetchall()]

    def fetch_rows_for_periods(
        self,
        project_id: str,
        sheet_name: str,
        financial_type: str | None,
        item_code: str | None,
        periods: list[tuple[int, int]],
        is_active: bool = True,
    ) -> list[FinancialRow]:
        import psycopg2.extras  # type: ignore

        if not periods:
            return []

        conditions = ["project_id = %s", "sheet_name = %s"]
        params: list = [project_id, sheet_name]

        if is_active:
            conditions.append("is_active = TRUE")
        if financial_type is not None:
            conditions.append("financial_type = %s")
            params.append(financial_type)
        if item_code is not None:
            conditions.append("item_code = %s")
            params.append(item_code)

        placeholders = ",".join(["(%s,%s)"] * len(periods))
        conditions.append(f"(report_month, report_year) IN ({placeholders})")
        for m, y in periods:
            params.extend([m, y])

        sql = (
            "SELECT project_id, sheet_name, report_month, report_year, "
            "financial_type, item_code, data_type, friendly_name, category, tier, value "
            "FROM normalized_financial_rows WHERE "
            + " AND ".join(conditions)
            + " ORDER BY report_year, report_month"
        )
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [_pg_row_to_financial_row(dict(r)) for r in cur.fetchall()]

    def get_latest_period(
        self,
        project_id: str,
        sheet_name: str,
        financial_type: str | None = None,
    ) -> tuple[int, int] | None:
        conditions = ["project_id = %s", "sheet_name = %s", "is_active = TRUE"]
        params: list = [project_id, sheet_name]
        if financial_type is not None:
            conditions.append("financial_type = %s")
            params.append(financial_type)
        sql = (
            "SELECT report_month, report_year FROM normalized_financial_rows WHERE "
            + " AND ".join(conditions)
            + " ORDER BY report_year DESC, report_month DESC LIMIT 1"
        )
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return (row[0], row[1]) if row else None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pg_row_to_financial_row(r: dict) -> FinancialRow:
    return FinancialRow(
        project_id=str(r["project_id"]),
        sheet_name=r["sheet_name"],
        report_month=r["report_month"],
        report_year=r["report_year"],
        financial_type=r["financial_type"],
        item_code=r["item_code"],
        data_type=r["data_type"],
        friendly_name=r["friendly_name"],
        category=r["category"],
        tier=r["tier"],
        value=float(r["value"]) if r["value"] is not None else None,
    )


def _format_period(month: int | None, year: int | None) -> str:
    if month and year:
        return f"{MONTH_LABELS[month - 1]} {year}"
    if year:
        return str(year)
    if month:
        return MONTH_LABELS[month - 1]
    return "—"


def _months_back(
    anchor_month: int, anchor_year: int, n: int
) -> list[tuple[int, int]]:
    """Return the last n (month, year) periods ending at anchor, chronological order."""
    periods: list[tuple[int, int]] = []
    m, y = anchor_month, anchor_year
    for _ in range(n):
        periods.append((m, y))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(periods))


def _item_code_sort_key(code: str | None) -> tuple[int, ...]:
    if not code:
        return (9999,)
    try:
        return tuple(int(x) for x in code.split("."))
    except ValueError:
        return (9999,)


# ── Shortcut Engine ───────────────────────────────────────────────────────────

class ShortcutEngine:
    """
    Executes a resolved query and returns a typed result payload.

    Args:
        provider:    DataProvider for normalized_financial_rows access.
        heading_map: {item_code: {data_type, friendly_name, category, tier}}
                     Required for List, Total, Detail, and Risk shortcuts.
    """

    def __init__(
        self,
        provider: DataProvider,
        heading_map: dict[str, dict] | None = None,
    ) -> None:
        self._provider = provider
        self._heading_map: dict[str, dict] = heading_map or {}

    def execute(self, resolved: ResolvedQuery) -> ExecutionResult:
        shortcut = resolved.shortcut
        warnings = list(resolved.warnings)

        if shortcut == "Shortcut":
            return self._shortcut_help(warnings)
        if shortcut == "Type":
            return self._type_list(warnings)
        if shortcut == "List":
            return self._list(resolved, warnings)
        if shortcut == "Total":
            if resolved.shortcut_b == "Compare":
                return self._total_compare(resolved, warnings)
            return self._total(resolved, warnings)
        if shortcut == "Detail":
            return self._detail(resolved, warnings)
        if shortcut == "Analyze":
            return self._analyze(resolved, warnings)
        if shortcut == "Risk":
            return self._risk(resolved, warnings)
        if shortcut == "Cash Flow Shortcut":
            return self._cash_flow_shortcut(resolved, warnings)
        if shortcut == "Compare":
            return self._compare(resolved, warnings)
        if shortcut == "Trend":
            if resolved.shortcut_b == "Compare":
                return self._trend_compare(resolved, warnings)
            return self._trend(resolved, warnings)

        # No shortcut — direct value retrieval
        return self._retrieve_value(resolved, warnings)

    # ── Period resolution helper ──────────────────────────────────────────────

    def _resolve_period(
        self,
        r: ResolvedQuery,
        sheet_name: str,
        financial_type: str | None = None,
    ) -> tuple[int, int] | None:
        if r.month and r.year:
            return (r.month, r.year)
        return self._provider.get_latest_period(r.project_id or "", sheet_name, financial_type)

    # ── Direct value retrieval ────────────────────────────────────────────────

    def _retrieve_value(self, r: ResolvedQuery, warnings: list[str]) -> ExecutionResult:
        if not r.project_id or not r.sheet_name:
            return NoDataResult(
                reason="Missing project or sheet — cannot retrieve value.",
                warnings=warnings,
            )
        period = self._resolve_period(r, r.sheet_name, r.financial_type)
        rows = self._provider.fetch_rows(
            r.project_id,
            r.sheet_name,
            financial_type=r.financial_type,
            item_code=r.item_code,
            data_type=r.data_type if not r.item_code else None,
            report_month=period[0] if period else r.month,
            report_year=period[1] if period else r.year,
        )
        if not rows:
            label = r.friendly_name or r.data_type or r.item_code or "requested item"
            return NoDataResult(
                reason=f"No data found for '{label}' in {r.sheet_name} "
                       f"({_format_period(r.month, r.year)}).",
                warnings=warnings,
            )
        row = rows[0]
        return ValueResult(
            label=row.friendly_name or row.data_type or "",
            value=row.value,
            project=r.project_name or r.project_code or "",
            period=_format_period(row.report_month, row.report_year),
            financial_type=row.financial_type or "",
            data_type=row.data_type or "",
            item_code=row.item_code or "",
            warnings=warnings,
        )

    # ── Shortcut / Type (static) ──────────────────────────────────────────────

    def _shortcut_help(self, warnings: list[str]) -> ShortcutHelpResult:
        return ShortcutHelpResult(items=_SHORTCUT_DESCRIPTIONS, warnings=warnings)

    def _type_list(self, warnings: list[str]) -> TypeListResult:
        return TypeListResult(items=_FINANCIAL_TYPE_REFS, warnings=warnings)

    # ── List ──────────────────────────────────────────────────────────────────

    def _list(self, r: ResolvedQuery, warnings: list[str]) -> ExecutionResult:
        parent_code = r.item_code

        if parent_code:
            items = [
                {
                    "Item Code": code,
                    "Friendly Name": h["friendly_name"],
                    "Data Type": h["data_type"],
                    "Tier": h["tier"],
                    "Category": h["category"],
                }
                for code, h in sorted(
                    self._heading_map.items(), key=lambda x: _item_code_sort_key(x[0])
                )
                if code == parent_code or code.startswith(parent_code + ".")
            ]
            if not items:
                return NoDataResult(
                    reason=f"No items found under item code {parent_code}.",
                    warnings=warnings,
                )
            return TableResult(
                shortcut="List",
                title=f"Items under {parent_code}",
                columns=["Item Code", "Friendly Name", "Data Type", "Tier", "Category"],
                rows=items,
                warnings=warnings,
            )

        # No item code — tier 1 and tier 2 only
        items = [
            {
                "Item Code": code,
                "Friendly Name": h["friendly_name"],
                "Data Type": h["data_type"],
                "Tier": h["tier"],
                "Category": h["category"],
            }
            for code, h in sorted(
                self._heading_map.items(), key=lambda x: _item_code_sort_key(x[0])
            )
            if code and h["tier"] in (1, 2)
        ]
        if not items:
            return NoDataResult(reason="No heading data available.", warnings=warnings)
        return TableResult(
            shortcut="List",
            title="Tier 1 and Tier 2 Items",
            columns=["Item Code", "Friendly Name", "Data Type", "Tier", "Category"],
            rows=items,
            warnings=warnings,
        )

    # ── Total ─────────────────────────────────────────────────────────────────

    def _total(self, r: ResolvedQuery, warnings: list[str]) -> ExecutionResult:
        if not r.project_id or not r.sheet_name or not r.item_code:
            return NoDataResult(
                reason="Total requires a project, sheet, and item code.",
                warnings=warnings,
            )
        period = self._resolve_period(r, r.sheet_name, r.financial_type)
        rows = self._provider.fetch_rows(
            r.project_id,
            r.sheet_name,
            financial_type=r.financial_type,
            report_month=period[0] if period else r.month,
            report_year=period[1] if period else r.year,
            item_code_prefix=r.item_code,
        )
        if not rows:
            return NoDataResult(
                reason=f"No data found for {r.friendly_name or r.item_code} "
                       f"in {r.sheet_name} ({_format_period(r.month, r.year)}).",
                warnings=warnings,
            )

        parent_depth = len(r.item_code.split("."))
        sorted_rows = sorted(rows, key=lambda x: _item_code_sort_key(x.item_code))

        # Immediate children only (one level deeper than parent)
        direct_children = [
            row for row in sorted_rows
            if row.item_code and len(row.item_code.split(".")) == parent_depth + 1
        ]
        subtotal = sum(row.value for row in direct_children if row.value is not None)

        table_rows = [
            {
                "Item Code": row.item_code,
                "Friendly Name": row.friendly_name or row.data_type or "",
                "Value": row.value,
            }
            for row in sorted_rows
            if row.item_code and len(row.item_code.split(".")) == parent_depth + 1
        ]

        # Include the parent row itself (the recorded total)
        parent_row = next((row for row in sorted_rows if row.item_code == r.item_code), None)
        footer = {
            "Item Code": r.item_code,
            "Friendly Name": f"Total ({r.friendly_name or r.item_code})",
            "Value": parent_row.value if parent_row else subtotal,
        }

        ft_label = f" / {r.financial_type}" if r.financial_type else ""
        p_label = _format_period(period[0] if period else r.month, period[1] if period else r.year)
        return TableResult(
            shortcut="Total",
            title=f"Total: {r.friendly_name or r.item_code}{ft_label} — {p_label}",
            columns=["Item Code", "Friendly Name", "Value"],
            rows=table_rows,
            footer=footer,
            warnings=warnings,
        )

    # ── Detail ────────────────────────────────────────────────────────────────

    def _detail(self, r: ResolvedQuery, warnings: list[str]) -> ExecutionResult:
        if not r.project_id or not r.sheet_name or not r.item_code:
            return NoDataResult(
                reason="Detail requires a project, sheet, and item code.",
                warnings=warnings,
            )
        period = self._resolve_period(r, r.sheet_name, r.financial_type)
        rows = self._provider.fetch_rows(
            r.project_id,
            r.sheet_name,
            financial_type=r.financial_type,
            report_month=period[0] if period else r.month,
            report_year=period[1] if period else r.year,
            item_code_prefix=r.item_code,
        )
        if not rows:
            return NoDataResult(
                reason=f"No data found for {r.friendly_name or r.item_code} "
                       f"in {r.sheet_name} ({_format_period(r.month, r.year)}).",
                warnings=warnings,
            )

        sorted_rows = sorted(rows, key=lambda x: _item_code_sort_key(x.item_code))
        # Exclude the parent row itself — Detail shows the children
        parent_depth = len(r.item_code.split("."))
        child_rows = [row for row in sorted_rows if row.item_code != r.item_code]

        if not child_rows:
            return NoDataResult(
                reason=f"No child items found under {r.friendly_name or r.item_code}.",
                warnings=warnings,
            )

        table_rows = [
            {
                "Item Code": row.item_code,
                "Friendly Name": row.friendly_name or row.data_type or "",
                "Tier": row.tier,
                "Value": row.value,
            }
            for row in child_rows
        ]

        ft_label = f" / {r.financial_type}" if r.financial_type else ""
        p_label = _format_period(period[0] if period else r.month, period[1] if period else r.year)
        return TableResult(
            shortcut="Detail",
            title=f"Detail: {r.friendly_name or r.item_code}{ft_label} — {p_label}",
            columns=["Item Code", "Friendly Name", "Tier", "Value"],
            rows=table_rows,
            warnings=warnings,
        )

    # ── Analyze ───────────────────────────────────────────────────────────────

    def _analyze(self, r: ResolvedQuery, warnings: list[str]) -> ExecutionResult:
        if not r.project_id:
            return NoDataResult(reason="Missing project for Analyze.", warnings=warnings)

        sheet = SNAPSHOT_SHEET
        period = self._resolve_period(r, sheet)
        if period is None:
            return NoDataResult(
                reason="No Financial Status data found for this project.",
                warnings=warnings,
            )
        month, year = period
        exception_rows: list[dict] = []

        for ft_proj, ft_compare, category, condition in _ANALYZE_RULES:
            proj_map = {
                row.item_code: row
                for row in self._provider.fetch_rows(
                    r.project_id, sheet,
                    financial_type=ft_proj,
                    report_month=month, report_year=year,
                )
                if row.tier in (1, 2) and row.category == category and row.item_code
            }
            comp_map = {
                row.item_code: row
                for row in self._provider.fetch_rows(
                    r.project_id, sheet,
                    financial_type=ft_compare,
                    report_month=month, report_year=year,
                )
                if row.tier in (1, 2) and row.category == category and row.item_code
            }

            for code in sorted(proj_map, key=_item_code_sort_key):
                row_proj = proj_map[code]
                row_comp = comp_map.get(code)
                if row_comp is None:
                    continue
                val_proj = row_proj.value
                val_comp = row_comp.value
                if val_proj is None or val_comp is None:
                    continue
                is_exception = (
                    condition == "proj_less_b" and val_proj < val_comp
                ) or (
                    condition == "proj_greater_b" and val_proj > val_comp
                )
                if is_exception:
                    exception_rows.append({
                        "Item Code": code,
                        "Friendly Name": row_proj.friendly_name or row_proj.data_type or "",
                        "Category": category,
                        "Rule": f"Projection vs {ft_compare}",
                        "Projection": val_proj,
                        "Comparison": val_comp,
                        "Difference": val_proj - val_comp,
                    })

        p_label = _format_period(month, year)
        if not exception_rows:
            return TableResult(
                shortcut="Analyze",
                title=f"Analysis: No exceptions found — {p_label}",
                columns=["Item Code", "Friendly Name", "Category", "Rule",
                         "Projection", "Comparison", "Difference"],
                rows=[],
                warnings=warnings,
            )

        return TableResult(
            shortcut="Analyze",
            title=f"Analysis Exceptions — {p_label}",
            columns=["Item Code", "Friendly Name", "Category", "Rule",
                     "Projection", "Comparison", "Difference"],
            rows=exception_rows,
            warnings=warnings,
        )

    # ── Risk ──────────────────────────────────────────────────────────────────

    def _risk(self, r: ResolvedQuery, warnings: list[str]) -> ExecutionResult:
        if not r.project_id:
            return NoDataResult(reason="Missing project for Risk.", warnings=warnings)

        sheet = SNAPSHOT_SHEET
        period = self._resolve_period(r, sheet)
        if period is None:
            return NoDataResult(
                reason="No Financial Status data found for this project.",
                warnings=warnings,
            )
        month, year = period

        rows_by_ft: dict[str, dict[str, FinancialRow]] = {}
        for ft in _RISK_FT_COLUMNS:
            rows = self._provider.fetch_rows(
                r.project_id, sheet,
                financial_type=ft,
                report_month=month, report_year=year,
            )
            rows_by_ft[ft] = {row.item_code: row for row in rows if row.item_code}

        all_codes = _RISK_INCOME_CODES + _RISK_COST_CODES
        table_rows: list[dict] = []
        for code in all_codes:
            meta = self._heading_map.get(code)
            friendly = meta["friendly_name"] if meta else code
            category = meta["category"] if meta else ""
            row_dict: dict = {
                "Item Code": code,
                "Friendly Name": friendly,
                "Category": category,
            }
            has_data = False
            for ft in _RISK_FT_COLUMNS:
                ft_row = rows_by_ft.get(ft, {}).get(code)
                row_dict[ft] = ft_row.value if ft_row else None
                if ft_row and ft_row.value is not None:
                    has_data = True
            if has_data:
                table_rows.append(row_dict)

        if not table_rows:
            return NoDataResult(
                reason=f"No risk data found in Financial Status "
                       f"({_format_period(month, year)}).",
                warnings=warnings,
            )

        return TableResult(
            shortcut="Risk",
            title=f"Risk Summary — {_format_period(month, year)}",
            columns=["Item Code", "Friendly Name", "Category"] + _RISK_FT_COLUMNS,
            rows=table_rows,
            warnings=warnings,
        )

    # ── Cash Flow Shortcut ────────────────────────────────────────────────────

    def _cash_flow_shortcut(self, r: ResolvedQuery, warnings: list[str]) -> ExecutionResult:
        if not r.project_id:
            return NoDataResult(
                reason="Missing project for Cash Flow shortcut.", warnings=warnings
            )

        sheet = "Cash Flow"
        anchor = self._provider.get_latest_period(r.project_id, sheet)
        if anchor is None:
            return NoDataResult(
                reason="No Cash Flow data found for this project.", warnings=warnings
            )

        periods = _months_back(anchor[0], anchor[1], 12)
        values_by_code: dict[str, dict[tuple[int, int], float]] = {
            code: {} for code, _ in _CASH_FLOW_ITEMS
        }
        for code, _ in _CASH_FLOW_ITEMS:
            for row in self._provider.fetch_rows_for_periods(
                r.project_id, sheet,
                financial_type=None,
                item_code=code,
                periods=periods,
            ):
                if row.value is not None:
                    values_by_code[code][(row.report_month, row.report_year)] = row.value

        item_names = [name for _, name in _CASH_FLOW_ITEMS]
        table_rows: list[dict] = []
        for m, y in periods:
            key = (m, y)
            row_dict: dict = {"Period": _format_period(m, y)}
            has_data = False
            for code, name in _CASH_FLOW_ITEMS:
                val = values_by_code[code].get(key)
                row_dict[name] = val
                if val is not None:
                    has_data = True
            if has_data:
                table_rows.append(row_dict)

        if not table_rows:
            return NoDataResult(
                reason="No Cash Flow data available for the requested period.",
                warnings=warnings,
            )

        return TableResult(
            shortcut="Cash Flow Shortcut",
            title="Cash Flow — Gross Profit (last 12 months)",
            columns=["Period"] + item_names,
            rows=table_rows,
            warnings=warnings,
        )

    # ── Compare ───────────────────────────────────────────────────────────────

    def _compare(self, r: ResolvedQuery, warnings: list[str]) -> ExecutionResult:
        if not r.project_id:
            return NoDataResult(reason="Missing project for Compare.", warnings=warnings)
        if not r.compare_a or not r.compare_b:
            return NoDataResult(
                reason="Compare requires two sides (use: compare A vs B).",
                warnings=warnings,
            )

        sheet_a = r.compare_a.sheet_name or r.sheet_name or SNAPSHOT_SHEET
        sheet_b = r.compare_b.sheet_name or r.sheet_name or SNAPSHOT_SHEET

        # Use a shared period for both sides
        if r.month and r.year:
            period = (r.month, r.year)
        else:
            period = (
                self._provider.get_latest_period(
                    r.project_id, sheet_a, r.compare_a.financial_type
                )
                or self._provider.get_latest_period(
                    r.project_id, sheet_b, r.compare_b.financial_type
                )
            )

        month = period[0] if period else r.month
        year = period[1] if period else r.year

        rows_a = self._provider.fetch_rows(
            r.project_id, sheet_a,
            financial_type=r.compare_a.financial_type,
            item_code=r.compare_a.item_code,
            data_type=r.compare_a.data_type if not r.compare_a.item_code else None,
            report_month=month, report_year=year,
        )
        rows_b = self._provider.fetch_rows(
            r.project_id, sheet_b,
            financial_type=r.compare_b.financial_type,
            item_code=r.compare_b.item_code,
            data_type=r.compare_b.data_type if not r.compare_b.item_code else None,
            report_month=month, report_year=year,
        )

        if not rows_a and not rows_b:
            return NoDataResult(
                reason="No data found for either comparison side.",
                warnings=warnings,
            )

        label_a = r.compare_a.friendly_name or r.compare_a.data_type or "Side A"
        label_b = r.compare_b.friendly_name or r.compare_b.data_type or "Side B"
        ft_a = r.compare_a.financial_type or ""
        ft_b = r.compare_b.financial_type or ""
        header_a = f"{label_a} ({ft_a})" if ft_a else label_a
        header_b = f"{label_b} ({ft_b})" if ft_b else label_b

        val_a = rows_a[0].value if rows_a else None
        val_b = rows_b[0].value if rows_b else None
        diff = (val_a - val_b) if val_a is not None and val_b is not None else None

        if not rows_a:
            warnings.append(f"No data found for {header_a}.")
        if not rows_b:
            warnings.append(f"No data found for {header_b}.")

        return TableResult(
            shortcut="Compare",
            title=f"Compare: {header_a} vs {header_b} — {_format_period(month, year)}",
            columns=["", header_a, header_b, "Difference"],
            rows=[
                {
                    "": label_a,
                    header_a: val_a,
                    header_b: val_b,
                    "Difference": diff,
                }
            ],
            warnings=warnings,
        )

    # ── Trend ─────────────────────────────────────────────────────────────────

    def _trend(self, r: ResolvedQuery, warnings: list[str]) -> ExecutionResult:
        if not r.project_id or not r.sheet_name:
            return NoDataResult(reason="Missing project or sheet for Trend.", warnings=warnings)

        num_months = r.num_months or 6

        if r.month and r.year:
            anchor = (r.month, r.year)
        else:
            anchor = self._provider.get_latest_period(
                r.project_id, r.sheet_name, r.financial_type
            )
        if anchor is None:
            return NoDataResult(
                reason="No data available for Trend — cannot determine period.",
                warnings=warnings,
            )

        periods = _months_back(anchor[0], anchor[1], num_months)
        rows = self._provider.fetch_rows_for_periods(
            r.project_id, r.sheet_name,
            r.financial_type, r.item_code, periods,
        )
        period_values: dict[tuple[int, int], float | None] = {}
        for row in rows:
            period_values[(row.report_month, row.report_year)] = row.value

        table_rows = [
            {"Period": _format_period(m, y), "Value": period_values.get((m, y))}
            for m, y in periods
        ]
        if not any(row["Value"] is not None for row in table_rows):
            return NoDataResult(
                reason=f"No trend data found for "
                       f"{r.friendly_name or r.data_type or r.item_code or 'requested item'} "
                       f"over the last {num_months} months.",
                warnings=warnings,
            )

        label = r.friendly_name or r.data_type or r.item_code or ""
        ft_label = f" ({r.financial_type})" if r.financial_type else ""
        return TableResult(
            shortcut="Trend",
            title=f"Trend: {label}{ft_label} — last {num_months} months",
            columns=["Period", "Value"],
            rows=table_rows,
            warnings=warnings,
        )

    # ── Trend Compare ─────────────────────────────────────────────────────────

    def _trend_compare(self, r: ResolvedQuery, warnings: list[str]) -> ExecutionResult:
        if not r.project_id:
            return NoDataResult(reason="Missing project for Trend Compare.", warnings=warnings)
        if not r.compare_a or not r.compare_b:
            return NoDataResult(
                reason="Trend Compare requires two sides (use: trend compare A vs B).",
                warnings=warnings,
            )

        num_months = r.num_months or 6
        sheet_a = r.compare_a.sheet_name or r.sheet_name or SNAPSHOT_SHEET
        sheet_b = r.compare_b.sheet_name or r.sheet_name or SNAPSHOT_SHEET

        if r.month and r.year:
            anchor = (r.month, r.year)
        else:
            anchor = (
                self._provider.get_latest_period(
                    r.project_id, sheet_a, r.compare_a.financial_type
                )
                or self._provider.get_latest_period(
                    r.project_id, sheet_b, r.compare_b.financial_type
                )
            )
        if anchor is None:
            return NoDataResult(
                reason="No data available for Trend Compare.", warnings=warnings
            )

        periods = _months_back(anchor[0], anchor[1], num_months)
        label_a = r.compare_a.friendly_name or r.compare_a.data_type or "Side A"
        label_b = r.compare_b.friendly_name or r.compare_b.data_type or "Side B"
        ft_a = r.compare_a.financial_type or ""
        ft_b = r.compare_b.financial_type or ""
        header_a = f"{label_a} ({ft_a})" if ft_a else label_a
        header_b = f"{label_b} ({ft_b})" if ft_b else label_b

        vals_a: dict[tuple[int, int], float] = {
            (row.report_month, row.report_year): row.value  # type: ignore[misc]
            for row in self._provider.fetch_rows_for_periods(
                r.project_id, sheet_a, r.compare_a.financial_type, r.compare_a.item_code, periods
            )
            if row.value is not None
        }
        vals_b: dict[tuple[int, int], float] = {
            (row.report_month, row.report_year): row.value  # type: ignore[misc]
            for row in self._provider.fetch_rows_for_periods(
                r.project_id, sheet_b, r.compare_b.financial_type, r.compare_b.item_code, periods
            )
            if row.value is not None
        }

        table_rows = []
        for m, y in periods:
            key = (m, y)
            val_a = vals_a.get(key)
            val_b = vals_b.get(key)
            diff = (val_a - val_b) if val_a is not None and val_b is not None else None
            table_rows.append(
                {"Period": _format_period(m, y), header_a: val_a, header_b: val_b, "Difference": diff}
            )

        if not any(row.get(header_a) is not None or row.get(header_b) is not None for row in table_rows):
            return NoDataResult(reason="No data found for Trend Compare.", warnings=warnings)

        return TableResult(
            shortcut="Trend",
            title=f"Trend Compare: {header_a} vs {header_b} — last {num_months} months",
            columns=["Period", header_a, header_b, "Difference"],
            rows=table_rows,
            warnings=warnings,
        )

    # ── Total Compare ─────────────────────────────────────────────────────────

    def _total_compare(self, r: ResolvedQuery, warnings: list[str]) -> ExecutionResult:
        if not r.project_id:
            return NoDataResult(reason="Missing project for Total Compare.", warnings=warnings)
        if not r.compare_a or not r.compare_b:
            return NoDataResult(
                reason="Total Compare requires two sides (use: total compare A vs B).",
                warnings=warnings,
            )

        sheet_a = r.compare_a.sheet_name or r.sheet_name or SNAPSHOT_SHEET
        sheet_b = r.compare_b.sheet_name or r.sheet_name or SNAPSHOT_SHEET

        if r.month and r.year:
            period = (r.month, r.year)
        else:
            period = (
                self._provider.get_latest_period(
                    r.project_id, sheet_a, r.compare_a.financial_type
                )
                or self._provider.get_latest_period(
                    r.project_id, sheet_b, r.compare_b.financial_type
                )
            )

        month = period[0] if period else r.month
        year = period[1] if period else r.year

        rows_a = self._provider.fetch_rows(
            r.project_id, sheet_a,
            financial_type=r.compare_a.financial_type,
            report_month=month, report_year=year,
            item_code_prefix=r.compare_a.item_code,
        ) if r.compare_a.item_code else []

        rows_b = self._provider.fetch_rows(
            r.project_id, sheet_b,
            financial_type=r.compare_b.financial_type,
            report_month=month, report_year=year,
            item_code_prefix=r.compare_b.item_code,
        ) if r.compare_b.item_code else []

        if not rows_a and not rows_b:
            return NoDataResult(reason="No data found for Total Compare.", warnings=warnings)

        map_a = {row.item_code: row.value for row in rows_a if row.item_code}
        map_b = {row.item_code: row.value for row in rows_b if row.item_code}

        label_a = r.compare_a.friendly_name or r.compare_a.data_type or "Side A"
        label_b = r.compare_b.friendly_name or r.compare_b.data_type or "Side B"
        ft_a = r.compare_a.financial_type or ""
        ft_b = r.compare_b.financial_type or ""
        header_a = f"{label_a} ({ft_a})" if ft_a else label_a
        header_b = f"{label_b} ({ft_b})" if ft_b else label_b

        all_codes = sorted(set(map_a.keys()) | set(map_b.keys()), key=_item_code_sort_key)
        table_rows = []
        for code in all_codes:
            meta = self._heading_map.get(code)
            friendly = meta["friendly_name"] if meta else code
            val_a = map_a.get(code)
            val_b = map_b.get(code)
            diff = (val_a - val_b) if val_a is not None and val_b is not None else None
            table_rows.append(
                {
                    "Item Code": code,
                    "Friendly Name": friendly,
                    header_a: val_a,
                    header_b: val_b,
                    "Difference": diff,
                }
            )

        total_a = sum(v for v in map_a.values() if v is not None)
        total_b = sum(v for v in map_b.values() if v is not None)
        footer = {
            "Item Code": "",
            "Friendly Name": "Total",
            header_a: total_a,
            header_b: total_b,
            "Difference": total_a - total_b,
        }

        return TableResult(
            shortcut="Total",
            title=f"Total Compare: {header_a} vs {header_b} — {_format_period(month, year)}",
            columns=["Item Code", "Friendly Name", header_a, header_b, "Difference"],
            rows=table_rows,
            footer=footer,
            warnings=warnings,
        )
