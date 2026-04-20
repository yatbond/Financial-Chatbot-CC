# FinLens — Financial Chatbot

A web-based natural-language query interface over uploaded Excel monthly financial reports for construction projects.

## Structure

```
/
├── web/          Next.js 15 (App Router) — frontend + API routes
├── ingestion/    Python worker — Excel parsing, normalization, ingestion
├── docs/         Architecture and domain documentation
├── Ref CSV/      Canonical mapping files (financial_type_map.csv, construction_headings_enriched.csv)
└── Sample Spreadsheets/   Sample Excel reports for development
```

## Running Locally

### Web (Next.js)

```bash
cd web
npm install
cp ../.env.example .env.local   # fill in your values
npm run dev
```

Runs at `http://localhost:3000`.

### Ingestion Worker (Python)

```bash
cd ingestion
uv sync
cp ../.env.example .env         # fill in your values
uv run python src/main.py
```

### Tests

```bash
# Python
cd ingestion && uv run pytest

# Next.js lint + type-check
cd web && npm run lint && npm run build
```

## Documentation

- [Architecture](docs/architecture.md)
- [Data Model](docs/data-model.md)
- [Ingestion Pipeline](docs/ingestion.md)
- [Query Resolution](docs/query-resolution.md)
- [Admin Workflows](docs/admin-workflows.md)
- [Known Issues](docs/known-issues.md)

## Build Phases

| Phase | Scope |
|-------|-------|
| 0 | Repo foundation (this commit) |
| 1 | Database schema (Supabase migrations) |
| 2 | Auth + app shell (Clerk, project nav) |
| 3 | Upload pipeline (file storage, job queue) |
| 4 | Admin mapping (CSV upload, mapping tables) |
| 5 | Excel parsing (Python ingestion) |
| 6 | Source-of-truth + discrepancy detection |
| 7 | Query resolution engine |
| 8 | Shortcut engine (Analyze, Compare, Trend, …) |
| 9 | Chat UI |
| 10 | Verbose mode + trace panel |
| 11 | Admin dashboards |
| 12 | Testing + deployment |
