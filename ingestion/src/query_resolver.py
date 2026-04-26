"""
Query Resolution Engine — Phase 7

Deterministic, rule-based parser that resolves natural-language chatbot queries
into structured parameters. Produces resolution or ambiguity payloads only —
no data retrieval happens here.

Entry point: QueryResolver.resolve(query, context) → ResolutionResult | AmbiguityResult
"""

from __future__ import annotations

import copy
import csv
import io
import re
from dataclasses import dataclass, field

# ── Shortcut groupings ───────────────────────────────────────────────────────

# Shortcuts that always operate on Financial Status (snapshot) — no month needed.
# These bypass the snapshot-vs-monthly ambiguity check and default sheet to FS.
_SNAPSHOT_SHORTCUTS = frozenset({
    "Total", "Detail", "Analyze", "Risk", "Type", "Shortcut", "List",
})

# ── Sheet / financial type constants ─────────────────────────────────────────

STANDARD_SHEETS = frozenset({
    "Financial Status", "Projection", "Committed Cost", "Accrual", "Cash Flow"
})
MONTHLY_SHEETS = frozenset({"Projection", "Committed Cost", "Accrual", "Cash Flow"})
SNAPSHOT_SHEET = "Financial Status"
MONTHLY_FINANCIAL_TYPES = frozenset({"Projection", "Committed Cost", "Accrual", "Cash Flow"})

# Explicit sheet aliases only — monthly sheets are inferred from financial_type.
_EXPLICIT_SHEET_ALIASES: list[tuple[str, str]] = [
    ("financial status", "Financial Status"),
    ("fs", "Financial Status"),
]

# Month name → int (longest forms first for regex matching)
MONTH_NAMES: dict[str, int] = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}
_MONTH_RE = re.compile(
    r'\b(' + '|'.join(sorted(MONTH_NAMES, key=len, reverse=True)) + r')\b'
)

MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Shortcut detection patterns (word-boundary aware; order matters for "shortcuts" before "shortcut")
_SHORTCUT_PATTERNS: list[tuple[str, str]] = [
    ("shortcuts", "Shortcut"),
    ("shortcut",  "Shortcut"),
    ("analyse",   "Analyze"),
    ("analyze",   "Analyze"),
    ("compare",   "Compare"),
    ("trend",     "Trend"),
    ("total",     "Total"),
    ("detail",    "Detail"),
    ("risk",      "Risk"),
    ("type",      "Type"),
    ("list",      "List"),
]

# Item-code pattern (e.g. "2.2", "1", "2.1.3")
_ITEM_CODE_RE = re.compile(r'\b(\d+(?:\.\d+)*)\b')

# Year pattern
_YEAR_RE = re.compile(r'\b(20\d{2})\b')


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class ConversationContext:
    """Active context inherited from prior conversation turns."""
    project_id: str | None = None
    project_code: str | None = None
    project_name: str | None = None
    sheet_name: str | None = None
    financial_type: str | None = None
    data_type: str | None = None
    item_code: str | None = None
    month: int | None = None
    year: int | None = None
    last_shortcut: str | None = None
    report_month: int | None = None   # from active report upload
    report_year: int | None = None    # from active report upload


@dataclass
class ResolvedQuery:
    shortcut: str | None = None
    shortcut_b: str | None = None      # second shortcut (e.g. "Compare" in "Trend Compare")
    project_id: str | None = None
    project_code: str | None = None
    project_name: str | None = None
    sheet_name: str | None = None
    financial_type: str | None = None
    data_type: str | None = None
    item_code: str | None = None
    friendly_name: str | None = None
    category: str | None = None
    tier: int | None = None
    month: int | None = None
    year: int | None = None
    num_months: int | None = None
    compare_a: "FieldSet | None" = None  # for Compare shortcut
    compare_b: "FieldSet | None" = None
    context_used: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    banner: dict = field(default_factory=dict)


@dataclass
class FieldSet:
    """Partial field resolution for one side of a Compare query."""
    financial_type: str | None = None
    data_type: str | None = None
    item_code: str | None = None
    friendly_name: str | None = None
    sheet_name: str | None = None


@dataclass
class Interpretation:
    rank: int
    label: str
    resolved: ResolvedQuery
    confidence: str  # "exact" | "acronym" | "context" | "default" | "inferred"


@dataclass
class ResolutionResult:
    resolved: ResolvedQuery
    is_ambiguous: bool = False


@dataclass
class AmbiguityResult:
    is_ambiguous: bool = True
    reason: str = ""
    interpretations: list[Interpretation] = field(default_factory=list)
    partial: ResolvedQuery | None = None


# ── QueryResolver ─────────────────────────────────────────────────────────────

class QueryResolver:
    """
    Resolves a natural-language query into structured financial parameters.

    Constructed with in-memory mapping dicts derived from the admin CSV files.
    All resolution is deterministic — no LLM calls.
    """

    def __init__(
        self,
        financial_type_aliases: dict[str, str],     # lower-case alias → canonical financial type
        heading_map: dict[str, dict],               # item_code → heading record
        heading_aliases: dict[str, list[dict]],     # lower-case alias → list of heading records
        projects: list[dict] | None = None,         # [{id, code, name}]
    ) -> None:
        self.financial_type_aliases = financial_type_aliases
        self.heading_map = heading_map
        self.heading_aliases = heading_aliases
        self.projects = projects or []
        self._project_by_code: dict[str, dict] = {
            p["code"].lower(): p for p in self.projects if p.get("code")
        }
        self._project_by_name: dict[str, dict] = {
            p["name"].lower(): p for p in self.projects if p.get("name")
        }

    # ── Factory ──────────────────────────────────────────────────────────────

    @classmethod
    def from_csv_dicts(
        cls,
        financial_type_rows: list[dict],
        heading_rows: list[dict],
        projects: list[dict] | None = None,
    ) -> "QueryResolver":
        """Build from raw CSV row dicts (as returned by csv.DictReader)."""
        financial_type_aliases: dict[str, str] = {}

        for row in financial_type_rows:
            clean = (row.get("Clean_Financial_Type") or "").strip()
            if not clean or clean.startswith("*"):
                continue
            # Map the clean name itself
            financial_type_aliases[clean.lower()] = clean
            # Map each pipe-delimited alias
            for alias in (row.get("Acronyms") or "").split("|"):
                a = alias.strip().lower()
                if a:
                    financial_type_aliases[a] = clean

        heading_map: dict[str, dict] = {}
        heading_aliases: dict[str, list[dict]] = {}

        for row in heading_rows:
            item_code = (row.get("Item_Code") or "").strip()
            data_type = (row.get("Data_Type") or "").strip()
            friendly = (row.get("Friendly_Name") or "").strip()
            category = (row.get("Category") or "").strip()
            try:
                tier = int(row.get("Tier") or 0)
            except (ValueError, TypeError):
                tier = 0
            acronyms_raw = (row.get("Acronyms") or "").strip()

            record: dict = {
                "item_code": item_code or None,
                "data_type": data_type,
                "friendly_name": friendly,
                "category": category,
                "tier": tier,
            }

            if item_code:
                heading_map[item_code] = record

            for alias in acronyms_raw.split("|"):
                a = alias.strip().lower()
                if a:
                    heading_aliases.setdefault(a, []).append(record)
            if friendly:
                heading_aliases.setdefault(friendly.lower(), []).append(record)

        return cls(financial_type_aliases, heading_map, heading_aliases, projects)

    @classmethod
    def from_csv_strings(
        cls,
        financial_type_csv: str,
        heading_csv: str,
        projects: list[dict] | None = None,
    ) -> "QueryResolver":
        ft_rows = list(csv.DictReader(io.StringIO(financial_type_csv)))
        h_rows = list(csv.DictReader(io.StringIO(heading_csv)))
        return cls.from_csv_dicts(ft_rows, h_rows, projects)

    # ── Main resolve entry point ──────────────────────────────────────────────

    def resolve(
        self,
        query: str,
        context: ConversationContext | None = None,
    ) -> ResolutionResult | AmbiguityResult:
        """
        Parse and resolve a user query.

        Returns ResolutionResult when the query is unambiguous,
        or AmbiguityResult (with up to 5 ranked interpretations) when ambiguous.
        """
        ctx = context or ConversationContext()
        text = query.strip().lower()

        # 1. Detect shortcuts and strip their keywords from text
        shortcuts, text_after_shortcuts = _detect_shortcuts(text)
        primary = shortcuts[0] if shortcuts else None
        secondary = shortcuts[1] if len(shortcuts) > 1 else None

        # 2. For Compare: split on "vs" to get two halves
        compare_a_text: str | None = None
        compare_b_text: str | None = None
        if "Compare" in shortcuts and "vs" in text_after_shortcuts:
            vs_idx = text_after_shortcuts.index(" vs ")
            if vs_idx != -1:
                compare_a_text = text_after_shortcuts[:vs_idx].strip()
                compare_b_text = text_after_shortcuts[vs_idx + 4:].strip()
                # Remove num_months from compare_b_text — it belongs to Trend
                if primary == "Trend":
                    compare_b_text, _ = _strip_trailing_number(compare_b_text)
            text_after_shortcuts = text_after_shortcuts.replace(" vs ", " ", 1)

        # 3. Parse all fields from remaining text
        parse = self._parse_fields(text_after_shortcuts, primary, ctx)
        partial = parse["partial"]
        partial.shortcut = primary
        partial.shortcut_b = secondary

        # Resolve compare sides if present
        if compare_a_text is not None:
            partial.compare_a = self._resolve_fieldset(compare_a_text)
        if compare_b_text is not None:
            partial.compare_b = self._resolve_fieldset(compare_b_text)

        # Inherit project from context (always safe)
        if partial.project_id is None and ctx.project_id:
            partial.project_id = ctx.project_id
            partial.project_code = ctx.project_code
            partial.project_name = ctx.project_name
            partial.context_used.append("project")

        # 4. Detect ambiguity
        ambiguity = self._check_ambiguity(partial, parse, ctx)
        if ambiguity:
            return ambiguity

        # 5. Apply defaults (context inheritance + report period)
        self._apply_defaults(partial, ctx)

        # 6. Build interpretation banner
        partial.banner = _build_banner(partial)

        return ResolutionResult(resolved=partial)

    # ── Field parsing ─────────────────────────────────────────────────────────

    def _parse_fields(self, text: str, shortcut: str | None, ctx: ConversationContext) -> dict:
        """
        Scan text for financial type, data type, explicit sheet, month, year,
        item code, and number-of-months. Returns a dict with 'partial' plus
        raw match lists for ambiguity checking.
        """
        partial = ResolvedQuery()
        remaining = text

        sheet_matches: list[str] = []
        ft_matches: list[tuple[str, str]] = []    # (alias, canonical)
        dt_matches: list[tuple[str, dict]] = []   # (alias, heading record)
        month_matches: list[int] = []
        year_matches: list[int] = []
        num_months: int | None = None
        item_code_explicit: str | None = None

        # --- Explicit sheet aliases (financial status only in resolver) ---
        for alias, canonical in _EXPLICIT_SHEET_ALIASES:
            if alias in remaining:
                sheet_matches.append(canonical)
                remaining = remaining.replace(alias, " ", 1)

        # --- Financial type aliases (longest first to avoid partial matches) ---
        for alias, canonical in sorted(
            self.financial_type_aliases.items(), key=lambda x: len(x[0]), reverse=True
        ):
            pattern = r'(?<!\w)' + re.escape(alias) + r'(?!\w)'
            if re.search(pattern, remaining):
                ft_matches.append((alias, canonical))
                remaining = re.sub(pattern, ' ', remaining, count=1)

        # --- Year (4-digit) ---
        for m in _YEAR_RE.finditer(remaining):
            year_matches.append(int(m.group(1)))
        remaining = _YEAR_RE.sub(' ', remaining)

        # --- Month names ---
        for m in _MONTH_RE.finditer(remaining):
            month_matches.append(MONTH_NAMES[m.group(1)])
        remaining = _MONTH_RE.sub(' ', remaining)

        # --- Item codes (e.g. "2.2", "1", "2.1.3") before generic numbers ---
        for m in _ITEM_CODE_RE.finditer(remaining):
            candidate = m.group(1)
            if candidate in self.heading_map:
                item_code_explicit = candidate
                remaining = remaining[:m.start()] + ' ' + remaining[m.end():]
                break

        # --- Remaining numbers ---
        for m in re.finditer(r'\b(\d+)\b', remaining):
            n = int(m.group(1))
            if shortcut == "Trend":
                if num_months is None:
                    num_months = n
            elif 1 <= n <= 12:
                month_matches.append(n)
            # Ignore other standalone numbers (e.g. item code fragments not in map)

        # --- Data type aliases (longest first) ---
        for alias, records in sorted(
            self.heading_aliases.items(), key=lambda x: len(x[0]), reverse=True
        ):
            pattern = r'(?<!\w)' + re.escape(alias) + r'(?!\w)'
            if re.search(pattern, remaining):
                for r in records:
                    dt_matches.append((alias, r))
                remaining = re.sub(pattern, ' ', remaining, count=1)
                break  # only consume one alias per scan pass; re-scan if needed

        # Second pass for data type (in case first alias was a subset hit)
        if not dt_matches:
            for alias, records in sorted(
                self.heading_aliases.items(), key=lambda x: len(x[0]), reverse=True
            ):
                if alias in remaining:
                    for r in records:
                        dt_matches.append((alias, r))
                    break

        # --- Assign unambiguous resolved fields ---
        unique_sheets = list(dict.fromkeys(sheet_matches))
        if len(unique_sheets) == 1:
            partial.sheet_name = unique_sheets[0]

        unique_ft = list(dict.fromkeys(c for _, c in ft_matches))
        if len(unique_ft) == 1:
            partial.financial_type = unique_ft[0]

        unique_dt_keys = list(dict.fromkeys(r["data_type"] for _, r in dt_matches))
        if len(unique_dt_keys) == 1:
            rec = dt_matches[0][1]
            partial.data_type = rec["data_type"]
            partial.friendly_name = rec["friendly_name"]
            partial.item_code = rec["item_code"]
            partial.category = rec["category"]
            partial.tier = rec["tier"]

        if item_code_explicit and partial.item_code is None:
            partial.item_code = item_code_explicit
            rec = self.heading_map.get(item_code_explicit)
            if rec:
                partial.data_type = rec["data_type"]
                partial.friendly_name = rec["friendly_name"]
                partial.category = rec["category"]
                partial.tier = rec["tier"]

        if len(month_matches) == 1:
            partial.month = month_matches[0]

        if len(year_matches) == 1:
            partial.year = year_matches[0]

        if num_months is not None:
            partial.num_months = num_months
        elif shortcut == "Trend":
            partial.num_months = 6  # PRD §13.6 default

        return {
            "partial": partial,
            "sheet_matches": unique_sheets,
            "ft_matches": unique_ft,
            "dt_matches": dt_matches,
            "month_matches": month_matches,
            "year_matches": year_matches,
        }

    def _resolve_fieldset(self, text: str) -> FieldSet:
        """Resolve financial type + data type from a sub-query fragment (for Compare sides)."""
        fs = FieldSet()
        remaining = text

        for alias, canonical in sorted(
            self.financial_type_aliases.items(), key=lambda x: len(x[0]), reverse=True
        ):
            if alias in remaining:
                fs.financial_type = canonical
                remaining = remaining.replace(alias, " ", 1)
                break

        for alias, records in sorted(
            self.heading_aliases.items(), key=lambda x: len(x[0]), reverse=True
        ):
            if alias in remaining:
                rec = records[0]
                fs.data_type = rec["data_type"]
                fs.item_code = rec["item_code"]
                fs.friendly_name = rec["friendly_name"]
                break

        if fs.financial_type:
            fs.sheet_name = (
                fs.financial_type if fs.financial_type in MONTHLY_FINANCIAL_TYPES
                else SNAPSHOT_SHEET
            )
        return fs

    # ── Ambiguity detection ───────────────────────────────────────────────────

    def _check_ambiguity(
        self,
        partial: ResolvedQuery,
        parse: dict,
        ctx: ConversationContext,
    ) -> AmbiguityResult | None:
        shortcut = partial.shortcut

        # Effective month: what will be used after defaults are applied
        effective_month = partial.month or ctx.month or ctx.report_month

        # --- Multiple financial types in query text ---
        # Suppressed for Compare when both sides are already resolved (FTs belong to each side).
        unique_ft = parse["ft_matches"]
        is_compare = shortcut == "Compare" or partial.shortcut_b == "Compare"
        compare_resolved = is_compare and partial.compare_a and partial.compare_b
        if len(unique_ft) > 1 and not compare_resolved:
            interps = []
            for i, ft in enumerate(unique_ft[:5]):
                r = _clone(partial)
                r.financial_type = ft
                _infer_sheet(r)
                r.banner = _build_banner(r)
                interps.append(Interpretation(
                    rank=i + 1,
                    label=f"Financial Type = {ft}",
                    resolved=r,
                    confidence="exact" if i == 0 else "acronym",
                ))
            return AmbiguityResult(
                reason="Multiple financial types matched — please select one.",
                interpretations=interps,
                partial=partial,
            )

        # --- Multiple data types for the same alias ---
        dt_matches = parse["dt_matches"]
        unique_dt = list(dict.fromkeys(r["data_type"] for _, r in dt_matches))
        if len(unique_dt) > 1:
            interps = []
            for i, (alias, rec) in enumerate(dt_matches[:5]):
                r = _clone(partial)
                r.data_type = rec["data_type"]
                r.friendly_name = rec["friendly_name"]
                r.item_code = rec["item_code"]
                r.category = rec["category"]
                r.tier = rec["tier"]
                r.banner = _build_banner(r)
                interps.append(Interpretation(
                    rank=i + 1,
                    label=f"Data Type = {rec['friendly_name']} ({rec['item_code'] or 'no code'})",
                    resolved=r,
                    confidence="exact" if i == 0 else "acronym",
                ))
            return AmbiguityResult(
                reason="Multiple data types matched — please select one.",
                interpretations=interps,
                partial=partial,
            )

        # --- Trend without financial type (not inherited from context) ---
        # Suppressed when compare sides are both resolved (each side carries its own FT).
        if (
            shortcut == "Trend"
            and partial.financial_type is None
            and not ctx.financial_type
            and not (partial.compare_a and partial.compare_b)
        ):
            interps = []
            for i, ft in enumerate(sorted(MONTHLY_FINANCIAL_TYPES)):
                r = _clone(partial)
                r.financial_type = ft
                r.sheet_name = ft
                r.banner = _build_banner(r)
                interps.append(Interpretation(
                    rank=i + 1,
                    label=ft,
                    resolved=r,
                    confidence="inferred",
                ))
            return AmbiguityResult(
                reason="Trend requires a financial type — which monthly sheet do you want to trend?",
                interpretations=interps,
                partial=partial,
            )

        # --- Month present + no financial type + no sheet → which monthly sheet? ---
        if (
            partial.month is not None
            and partial.financial_type is None
            and partial.sheet_name is None
            and shortcut not in _SNAPSHOT_SHORTCUTS
            and not ctx.financial_type
        ):
            interps = []
            for i, ft in enumerate(sorted(MONTHLY_FINANCIAL_TYPES)):
                r = _clone(partial)
                r.financial_type = ft
                r.sheet_name = ft
                r.banner = _build_banner(r)
                interps.append(Interpretation(
                    rank=i + 1,
                    label=f"{ft} — {_format_period(partial.month, partial.year)}",
                    resolved=r,
                    confidence="inferred",
                ))
            return AmbiguityResult(
                reason="Month specified but no financial type — which monthly sheet?",
                interpretations=interps,
                partial=partial,
            )

        # --- Financial type without month → snapshot vs monthly ambiguity ---
        # Skipped for snapshot shortcuts (they always use Financial Status).
        # Skipped when context provides a month (defaults will route it correctly).
        if (
            partial.financial_type in MONTHLY_FINANCIAL_TYPES
            and effective_month is None
            and partial.sheet_name is None
            and shortcut not in _SNAPSHOT_SHORTCUTS
            and shortcut not in {"Trend", "Cash Flow Shortcut", "Compare"}
        ):
            snapshot_r = _clone(partial)
            snapshot_r.sheet_name = SNAPSHOT_SHEET
            snapshot_r.banner = _build_banner(snapshot_r)

            monthly_r = _clone(partial)
            monthly_r.sheet_name = partial.financial_type
            monthly_r.warnings = ["Please specify a month for the monthly sheet."]
            monthly_r.banner = _build_banner(monthly_r)

            return AmbiguityResult(
                reason=(
                    f"'{partial.financial_type}' can refer to the Financial Status snapshot "
                    "or the monthly sheet — which do you want?"
                ),
                interpretations=[
                    Interpretation(
                        rank=1,
                        label=f"Financial Status / {partial.financial_type} (snapshot)",
                        resolved=snapshot_r,
                        confidence="default",
                    ),
                    Interpretation(
                        rank=2,
                        label=f"{partial.financial_type} monthly sheet (specify month)",
                        resolved=monthly_r,
                        confidence="inferred",
                    ),
                ],
                partial=partial,
            )

        # --- No financial type, no sheet, data type present → multiple interpretations ---
        if (
            partial.data_type is not None
            and partial.financial_type is None
            and partial.sheet_name is None
            and effective_month is None
            and shortcut not in _SNAPSHOT_SHORTCUTS
            and not ctx.financial_type
            and not ctx.sheet_name
        ):
            interps_list: list[Interpretation] = []
            r0 = _clone(partial)
            r0.sheet_name = SNAPSHOT_SHEET
            r0.banner = _build_banner(r0)
            interps_list.append(Interpretation(
                rank=1, label="Financial Status (snapshot, all types)", resolved=r0, confidence="default",
            ))
            for i, ft in enumerate(sorted(MONTHLY_FINANCIAL_TYPES)):
                r = _clone(partial)
                r.financial_type = ft
                r.sheet_name = ft
                r.banner = _build_banner(r)
                interps_list.append(Interpretation(
                    rank=i + 2, label=f"{ft} (monthly — specify month)", resolved=r, confidence="inferred",
                ))
            return AmbiguityResult(
                reason="Financial type not specified — which financial type or sheet do you want?",
                interpretations=interps_list[:5],
                partial=partial,
            )

        # --- Multiple months ---
        if len(parse["month_matches"]) > 1:
            return AmbiguityResult(
                reason="Multiple month values detected — please clarify which month.",
                interpretations=[],
                partial=partial,
            )

        return None

    # ── Defaults ─────────────────────────────────────────────────────────────

    def _apply_defaults(self, partial: ResolvedQuery, ctx: ConversationContext) -> None:
        """Apply context inheritance and report-period defaults."""
        # Financial type from context
        if partial.financial_type is None and ctx.financial_type:
            partial.financial_type = ctx.financial_type
            partial.context_used.append("financial_type")

        # Data type from context
        if partial.data_type is None and ctx.data_type:
            partial.data_type = ctx.data_type
            partial.context_used.append("data_type")

        # Month/year defaults from report period, then conversation context
        # (applied before sheet inference so _infer_sheet sees the effective month)
        if partial.month is None:
            if ctx.report_month:
                partial.month = ctx.report_month
                partial.context_used.append("month (report default)")
            elif ctx.month:
                partial.month = ctx.month
                partial.context_used.append("month (context)")

        if partial.year is None:
            if ctx.report_year:
                partial.year = ctx.report_year
                partial.context_used.append("year (report default)")
            elif ctx.year:
                partial.year = ctx.year
                partial.context_used.append("year (context)")

        # Snapshot shortcuts always use Financial Status regardless of month
        if partial.sheet_name is None and partial.shortcut in _SNAPSHOT_SHORTCUTS:
            partial.sheet_name = SNAPSHOT_SHEET

        # Infer sheet from financial type (uses month which may now be set)
        _infer_sheet(partial)

        # Sheet from context (fallback)
        if partial.sheet_name is None and ctx.sheet_name:
            partial.sheet_name = ctx.sheet_name
            partial.context_used.append("sheet_name")

        # Trend against Financial Status warning (after sheet is resolved)
        if partial.shortcut == "Trend" and partial.sheet_name == SNAPSHOT_SHEET:
            partial.warnings.append(
                "Financial Status does not contain month-to-month movement history. "
                "Trend cannot be applied to Financial Status."
            )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _detect_shortcuts(text: str) -> tuple[list[str], str]:
    """
    Detect shortcut keywords in text.
    Returns (list of canonical shortcut names in left-to-right text order,
    text with shortcut words removed).
    """
    # Collect (position, canonical) pairs so we can sort by appearance
    hits: list[tuple[int, str]] = []
    remaining = text

    for kw, canonical in _SHORTCUT_PATTERNS:
        pattern = r'\b' + re.escape(kw) + r'\b'
        m = re.search(pattern, remaining)
        if m:
            hits.append((m.start(), canonical))
            remaining = re.sub(pattern, ' ', remaining, count=1)

    # "vs" → Compare (if "compare" not already found)
    if re.search(r'\bvs\b', remaining):
        m = re.search(r'\bvs\b', remaining)
        if m and not any(c == "Compare" for _, c in hits):
            hits.append((m.start(), "Compare"))
        # Don't strip "vs" here — _resolve handles the compare split

    # "cash flow" shortcut: only when no other shortcut was detected
    if not hits and re.search(r'\bcash\s+flow\b', remaining):
        hits.append((0, "Cash Flow Shortcut"))

    # Sort by text position; deduplicate preserving order
    hits.sort(key=lambda x: x[0])
    seen: set[str] = set()
    detected: list[str] = []
    for _, canonical in hits:
        if canonical not in seen:
            seen.add(canonical)
            detected.append(canonical)

    return detected, remaining.strip()


def _strip_trailing_number(text: str) -> tuple[str, int | None]:
    """Remove a trailing standalone number from text, return (stripped, number)."""
    m = re.search(r'\b(\d+)\s*$', text.strip())
    if m:
        return text[:m.start()].strip(), int(m.group(1))
    return text, None


def _infer_sheet(r: ResolvedQuery) -> None:
    """Set sheet_name from financial_type if not already set."""
    if r.sheet_name is not None:
        return
    if r.financial_type is None:
        return
    if r.financial_type in MONTHLY_FINANCIAL_TYPES and r.month is not None:
        r.sheet_name = r.financial_type
    elif r.financial_type not in MONTHLY_FINANCIAL_TYPES:
        r.sheet_name = SNAPSHOT_SHEET
    # If financial type is monthly-capable but no month: sheet remains None
    # (ambiguity handler deals with this before _apply_defaults is called)


def _clone(r: ResolvedQuery) -> ResolvedQuery:
    return copy.deepcopy(r)


def _build_banner(r: ResolvedQuery) -> dict:
    project_str = (
        f"{r.project_code} / {r.project_name}"
        if r.project_code and r.project_name
        else (r.project_code or r.project_name or "—")
    )
    return {
        "project": project_str,
        "shortcut": r.shortcut,
        "shortcut_b": r.shortcut_b,
        "sheet": r.sheet_name or "—",
        "financial_type": r.financial_type or "—",
        "data_type": r.friendly_name or r.data_type or "—",
        "item_code": r.item_code or "—",
        "period": _format_period(r.month, r.year),
        "num_months": r.num_months,
        "warnings": r.warnings,
    }


def _format_period(month: int | None, year: int | None) -> str:
    if month and year:
        return f"{MONTH_LABELS[month - 1]} {year}"
    if year:
        return str(year)
    if month:
        return MONTH_LABELS[month - 1]
    return "—"
