# Query Resolution Engine — Phase 7

Implementation: `ingestion/src/query_resolver.py`
Tests: `ingestion/tests/test_query_resolver.py`

## Entry Point

```python
from src.query_resolver import QueryResolver, ConversationContext

resolver = QueryResolver.from_csv_strings(financial_type_csv, heading_csv, projects)
result = resolver.resolve("projected gp", context)
# returns ResolutionResult or AmbiguityResult
```

## Result Schemas

### ResolutionResult
Returned when the query resolves without ambiguity.
```
resolved.shortcut          → "Trend" | "Compare" | ... | None
resolved.shortcut_b        → second shortcut (e.g. "Compare" in "Trend Compare")
resolved.project_id/code/name
resolved.sheet_name        → "Financial Status" | "Projection" | "Committed Cost" | "Accrual" | "Cash Flow"
resolved.financial_type    → canonical financial type from financial_type_map
resolved.data_type         → canonical data type from heading map
resolved.item_code         → e.g. "2.1", "3"
resolved.friendly_name     → official Friendly_Name from heading map
resolved.category          → "Income" | "Cost" | "Summary" | ...
resolved.tier              → 0–3
resolved.month             → 1–12 | None
resolved.year              → e.g. 2026 | None
resolved.num_months        → for Trend (default 6)
resolved.compare_a/b       → FieldSet (financial_type + data_type per side)
resolved.context_used      → list of fields inherited from context
resolved.warnings          → list of warning strings
resolved.banner            → dict for interpretation banner UI
```

### AmbiguityResult
Returned when the query cannot be resolved uniquely.
```
result.is_ambiguous        → True
result.reason              → human-readable reason string
result.interpretations     → list[Interpretation], up to 5, ranked
result.partial             → partially resolved ResolvedQuery (fields resolved so far)

Interpretation:
  .rank         → 1–5
  .label        → display label for the option
  .resolved     → fully resolved ResolvedQuery for this interpretation
  .confidence   → "exact" | "acronym" | "context" | "default" | "inferred"
```

## Resolution Fields

| Field | Source |
|---|---|
| Shortcut | Explicit keyword detection (PRD §13.1) |
| Project | Passed in via context |
| Sheet Name | Explicit alias ("fs", "financial status") or inferred from financial type + month |
| Financial Type | financial_type_map.csv aliases |
| Data Type / Item Code | construction_headings_enriched.csv aliases |
| Month | Month name / abbreviation / 1–12 number |
| Year | 4-digit year |
| Num Months | Number after "trend" keyword (default 6) |

## Shortcuts Detected

`Shortcut | Analyze | Compare | Trend | Total | Detail | Risk | Cash Flow Shortcut | Type | List`

Multi-shortcut combinations: `Trend Compare`, `Total Compare` — primary is left-most shortcut.

## Ambiguity Rules (PRD §10.2)

| Condition | Response |
|---|---|
| Multiple financial types matched | Show up to 5 FT options |
| Multiple data types matched | Show up to 5 DT options |
| Trend without financial type | Ask which monthly sheet |
| Month present, no financial type | Ask which monthly sheet |
| Financial type (monthly-capable) + no month + no context month | Ask snapshot vs monthly |
| Data type only (no FT, no sheet, no month) | Show FS + all monthly options |
| Multiple month values | Ask user to clarify |

## Snapshot vs Monthly Routing

**Snapshot shortcuts** (always use Financial Status, no month required):
`Total, Detail, Analyze, Risk, Type, Shortcut, List`

**Monthly routing**: When FT is monthly-capable (Projection, Committed Cost, Accrual, Cash Flow) AND month is present (from query or context), sheet = that financial type's sheet.

**Ambiguity**: When FT is monthly-capable, no month in query, and no month in context → ask.

## Context Memory Rules (PRD §11)

Inherited from `ConversationContext` when not ambiguous:
- `project_id/code/name` — always inherited
- `financial_type` — inherited when FT not in query
- `data_type` — inherited when DT not in query
- `sheet_name` — inherited as fallback after inference
- `month` — first from `report_month`, then from `ctx.month`
- `year` — first from `report_year`, then from `ctx.year`

`context_used` list records which fields were inherited.

## PRD Example Query Resolutions

| Query | Result |
|---|---|
| `projected gp` (no context) | Ambiguous — snapshot vs monthly |
| `projected gp` + ctx month | ResolutionResult — Projection monthly sheet |
| `compare projected gp vs wip gp` | Compare, compare_a=Projection/GP, compare_b=WIP/GP |
| `trend compare projection gp vs wip gp 8` | Trend+Compare, num_months=8, compare sides resolved |
| `total cost projected` | Total shortcut → Financial Status / Projection / Total Cost |
| `total prelim bp` | Total → FS / Business Plan / Preliminaries |
| `detail cash flow prelim` | Detail → FS / Cash Flow / Preliminaries |
| `risk` | Risk shortcut (resolved) |
| `list` | List shortcut (resolved) |
| `list 2.2` | List shortcut, item_code=2.2 |
| `committed prelim 8` + ctx year | Committed Cost / month=8 / Preliminaries |
| `prelim oct` (no FT in context) | Ambiguous — which monthly sheet? |
| `trend gp 8` (no FT) | Ambiguous — which monthly sheet? |
| `type` | Type shortcut (resolved) |
| `shortcut` | Shortcut shortcut (resolved) |
| `gp` (no context) | Ambiguous — FT needed |

## Warnings

- Trend against Financial Status: "Financial Status does not contain month-to-month movement history."
- Monthly sheet with no month: "Please specify a month for the monthly sheet."
