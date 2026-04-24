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
