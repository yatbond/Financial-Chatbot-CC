# Architecture

## System Overview

```
Browser
  └─ Next.js 15 (Vercel)
       ├─ App Router pages  (chat, projects, admin)
       ├─ Server Actions     (upload trigger, query execution)
       └─ Route Handlers     (REST endpoints for ingestion status)
            │
            ├─ Supabase Postgres   (normalized data, mappings, discrepancies, audit)
            ├─ Supabase Storage    (uploaded Excel reports, mapping CSVs)
            ├─ Clerk               (authentication, user identity)
            └─ Redis (BullMQ)      (ingestion job queue)
                 │
                 └─ Python Worker (Fly.io / Railway)
                      ├─ Excel parser   (openpyxl / xlrd)
                      ├─ Normalizer     (financial_type_map + heading_map)
                      ├─ Overlap detector
                      └─ Discrepancy recorder
```

## Four Core Engines

| Engine | Responsibility |
|--------|---------------|
| **Ingestion & Normalization** | Parse workbooks, normalize via mappings, detect overlaps, flag discrepancies |
| **Query Resolution** | Parse user query → structured parameters; rank ambiguity options |
| **Analytics** | Execute shortcut logic (Compare, Trend, Analyze, Risk, Cash Flow, etc.) |
| **Response & Traceability** | Format standard or verbose results with row/cell trace |

## Key Design Decisions

- **Deterministic query parsing** — rule-based, not LLM-interpreted
- **Ambiguity surfaced, never silently resolved** — up to 5 ranked options shown
- **Active-truth rule** — latest validated upload wins for overlapping monthly data; prior values retained for audit
- **Ingestion trigger** — Redis + BullMQ job queue; Next.js enqueues on upload, Python worker consumes
- **Hosting** — Vercel (web) + Supabase (DB/Storage) + Fly.io or Railway (Python worker + Redis)
