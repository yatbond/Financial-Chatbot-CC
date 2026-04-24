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
