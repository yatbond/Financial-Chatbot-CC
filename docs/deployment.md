# Deployment Guide

> Last updated: 2026-04-24. Internal use only.

## Prerequisites

- Node.js 20+, npm
- Python 3.12, uv
- Supabase project (Postgres + Storage)
- Clerk application (auth)
- Redis instance (Upstash or Railway)
- Vercel account (web)
- Fly.io or Railway account (ingestion service)

---

## Environment Variables

### Web (`web/.env.local`)

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key (public) |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key (server-only) |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Clerk publishable key |
| `CLERK_SECRET_KEY` | Clerk secret key (server-only) |
| `NEXT_PUBLIC_CLERK_SIGN_IN_URL` | `/sign-in` |
| `NEXT_PUBLIC_CLERK_SIGN_UP_URL` | `/sign-up` |
| `NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL` | `/projects` |
| `NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL` | `/projects` |

### Ingestion service (`ingestion/.env`)

| Variable | Description |
|---|---|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key |
| `DATABASE_URL` | Direct Postgres connection string (not pooler) |
| `INGESTION_PORT` | Port to bind (default: 8000) |

---

## Supabase Setup

1. **Run migrations** (all files in `web/supabase/migrations/` in order):
   ```
   supabase db push
   ```
   Or apply each `.sql` file manually via the Supabase SQL editor.

2. **Storage bucket** — create a private bucket named `mappings` and `reports`.
   - `mappings/`: stores uploaded CSV mapping files
   - `reports/`: stores uploaded Excel reports

3. **Row-Level Security** — RLS is configured per-migration. After applying migrations, verify:
   - `projects` table: users can only read projects they belong to
   - `normalized_financial_rows`: filtered by project membership
   - `query_logs`: filtered by project membership
   - `admin_notes`: no public read (admin-only)

   **Manual check:** In Supabase dashboard → Table Editor → each table → RLS enabled ✓

4. **Service role key** is required for the ingestion worker (bypasses RLS for inserts). Never expose this to the browser.

---

## Web Deployment (Vercel)

```bash
cd web
npm run build          # verify build succeeds locally first
```

1. Push to GitHub (main branch)
2. Import repository in Vercel
3. Set **Root Directory** to `web`
4. Add all environment variables from the table above
5. Deploy

**Post-deploy checks:**
- `GET /` → redirects to `/sign-in` ✓
- `POST /api/projects/<id>/chat` with valid session → returns JSON ✓
- Admin page loads without 500 errors ✓

---

## Ingestion Service Deployment (Fly.io)

```bash
cd ingestion
uv sync
fly launch --name finlens-ingestion --no-deploy
```

Add secrets:
```bash
fly secrets set SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... DATABASE_URL=...
```

Deploy:
```bash
fly deploy
```

Health check:
```bash
curl https://finlens-ingestion.fly.dev/health
# → {"status": "ok"}
```

**Note:** The ingestion service is currently triggered by a direct HTTP call from the web `/api/reports/upload` route, not via Redis/BullMQ. Redis queuing is deferred (see `docs/known-issues.md`).

---

## Production Checklist

### Before first deploy

- [ ] All migrations applied to production Supabase
- [ ] Storage buckets `mappings` and `reports` created (private)
- [ ] Clerk production application keys set (not development keys)
- [ ] `SUPABASE_SERVICE_ROLE_KEY` set in Vercel env — verify it is NOT prefixed with `NEXT_PUBLIC_`
- [ ] Ingestion service deployed and `/health` returns 200
- [ ] At least one project and user record in `projects` and `project_members` tables

### After first deploy

- [ ] Upload a sample CSV mapping (Financial Type Map) and confirm it applies
- [ ] Upload a sample Excel report and confirm ingestion succeeds (`validation_status = 'valid'`)
- [ ] Run a chat query and confirm a `query_logs` row is inserted
- [ ] Verify the Admin panel loads and shows the Mappings tab
- [ ] Verify "Export for Claude" downloads a `.md` file
- [ ] Check Supabase logs for any 500-level errors within 10 minutes of deploy

### Ongoing

- [ ] Monitor `query_logs` for `response_type = 'error'` spikes
- [ ] Monitor ingestion upload `validation_status = 'invalid'` rate
- [ ] Review open discrepancies weekly in the Admin panel
- [ ] Rotate `SUPABASE_SERVICE_ROLE_KEY` and `CLERK_SECRET_KEY` every 90 days

---

## Known Deployment Gotchas

1. **`SUPABASE_SERVICE_ROLE_KEY` must be server-only** — never prefix with `NEXT_PUBLIC_`. The web server passes it only to `createServerSupabase()` in server components and route handlers.

2. **Ingestion service DB connection** — use the direct connection string, not the Supabase pooler URL. The worker holds long-lived transactions during overlap resolution.

3. **Clerk domain** — Clerk requires the production domain to be added to "Allowed redirect origins" in the dashboard before sign-in works on the production URL.

4. **Next.js `params` and `searchParams`** — these are `Promise<...>` in this project. Any new page must `await params` before use, or you will get a hydration error.
