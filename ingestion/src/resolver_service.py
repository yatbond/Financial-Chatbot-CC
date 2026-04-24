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
