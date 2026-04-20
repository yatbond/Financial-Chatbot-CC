# Query Resolution

> Stub — to be filled in during Phase 7 (Query Resolution Engine).

## Planned Resolution Fields

- Shortcut keyword (Analyze, Compare, Trend, List, Total, Detail, Risk, Cash Flow, Type)
- Project Code / Project Name
- Sheet Name
- Financial Type
- Data Type
- Item Code
- Month / Year
- Number of Months (for Trend)
- Conversation context (session memory)

## Ambiguity Handling

If a query is ambiguous, show up to 5 ranked interpretation options. Never silently guess.

Ranking order:
1. Exact canonical match
2. Acronym/alias match
3. Conversation context match
4. Report month default match
5. Prior user behaviour match
