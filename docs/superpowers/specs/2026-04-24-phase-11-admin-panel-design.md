# Phase 11 — Admin Panel Design
**Date:** 2026-04-24
**Project:** FinLens Financial Chatbot
**Status:** Approved for implementation

---

## Overview

Build the Phase 11 admin panel: a three-tab admin page (Mappings | Query Logs | Discrepancies), inline discrepancy review, admin notes on query logs and mapping uploads, and an "Export for Claude" button that generates a structured markdown file for developer-assisted code fixes.

---

## Architecture

### URL-based state (App Router search params)

All tab, filter, and pagination state lives in URL search params. The admin page server component reads `searchParams` and fetches data accordingly. No client-side state for navigation.

```
/projects/[projectId]/admin                          → defaults to tab=mappings
/projects/[projectId]/admin?tab=query-logs           → Query Logs tab, page 1
/projects/[projectId]/admin?tab=query-logs&mode=standard&type=error&page=2
/projects/[projectId]/admin?tab=discrepancies        → Discrepancies tab
```

### Component split

- `admin/page.tsx` — server component, reads searchParams, fetches tab data, renders `AdminTabs` + active tab content
- `components/admin/AdminTabs.tsx` — `use client`, renders tab bar with Link navigation
- `components/admin/QueryLogsTab.tsx` — server component, receives pre-fetched logs + pagination metadata
- `components/admin/QueryLogRow.tsx` — `use client`, handles inline note expand/collapse
- `components/admin/DiscrepanciesTab.tsx` — server component, receives pre-fetched discrepancies
- `components/admin/DiscrepancyReviewRow.tsx` — `use client`, handles inline review expand/collapse
- `components/admin/ExportButton.tsx` — `use client`, triggers markdown download

### New server actions (`admin/actions.ts` additions)

| Action | Purpose |
|---|---|
| `getQueryLogs(projectId, filters, page)` | Fetch paginated query logs with optional mode/response_type filters. Returns `{ logs: QueryLog[], total: number }` |
| `getDiscrepancies(projectId)` | Fetch all `review_status = 'pending'` discrepancies |
| `reviewDiscrepancy(id, status, note)` | Auth-gated. Sets review_status to `reviewed` or `dismissed`; writes reviewer_note, reviewed_by (from `auth()`), reviewed_at |
| `saveAdminNote(entityType, entityId, projectId, note)` | Auth-gated. Upserts a row in `admin_notes`; created_by from `auth()` |
| `getAdminNotes(entityIds)` | Fetch notes for a set of entity IDs. Returns `Record<string, AdminNote>` keyed by `entity_id` |
| `exportIssues(projectId)` | Aggregate all admin_notes + pending discrepancy reviewer_notes. Returns structured JSON for client-side MD formatting |

---

## Tab 1: Mappings (no changes)

Existing content unchanged — mapping state stats, Financial Type Map upload/history, Heading Map upload/history.

**One addition:** each mapping upload history row gets a `+ Note` / `📝 Edit note` affordance using the shared inline note component (same pattern as query logs).

---

## Tab 2: Query Logs

### Data fetched (server)
- `query_logs` filtered by `project_id`, optional `mode`, optional `response_type`
- Ordered by `created_at DESC`
- Page size: 20. Total count via `{ count: 'exact', head: true }`.
- `admin_notes` for all log IDs on the current page, fetched via `getAdminNotes(logIds)` and passed as `Record<string, AdminNote>` keyed by entity_id

### Columns
| Column | Source field |
|---|---|
| Query | `raw_query` (truncated to ~80 chars, full text on hover) |
| Type | `response_type` (colour-coded badge) |
| Mode | `mode` |
| ms | `execution_ms` |
| When | `created_at` (formatted dd MMM HH:mm) |
| Note | `+ Note` link or `📝 Edit note` if note exists |

### Filters (URL params, rendered as `<select>` in a filter bar)
- `mode`: All modes / standard / verbose
- `type`: All response types / value / table / trend / compare / total / detail / risk / cash_flow / list / ambiguity / missing / error

Changing a filter resets `page` to 1.

### Pagination
- Previous / page numbers / Next links
- Show "Showing X–Y of Z" count

### Inline note
Clicking `+ Note` or `📝 Edit note` on a row expands a sub-row with:
- `<textarea>` pre-filled with existing note (if any)
- Save / Cancel buttons
- Saving calls `saveAdminNote('query_log', id, projectId, note)` then revalidates path
- At most one row open at a time

---

## Tab 3: Discrepancies

### Data fetched (server)
- `discrepancies` where `project_id = X` AND `review_status = 'pending'`
- Ordered by `detected_at DESC`

### Columns
| Column | Source field |
|---|---|
| Sheet | `sheet_name` |
| Period | `report_month` / `report_year` (formatted "Feb 2026") |
| Item | `data_type` or `item_code` |
| Old value | `old_value` (red) |
| New value | `new_value` (green) |
| Actions | Review · Dismiss links |

Shows a count header: "N open discrepancies".
Shows empty state if none pending.

### Inline review
Clicking **Review** or **Dismiss** on a row expands a sub-row with:
- `<textarea>` for optional note
- Confirm (labelled "Mark reviewed" or "Dismiss") / Cancel buttons
- One row open at a time
- Confirm calls `reviewDiscrepancy(id, status, note)` → sets `review_status`, `reviewer_note`, `reviewed_by` (from `auth()`), `reviewed_at` → revalidates path → row disappears from list

---

## Admin Notes System

### New DB table: `admin_notes`

```sql
CREATE TABLE admin_notes (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id  uuid REFERENCES projects(id) ON DELETE CASCADE,
  entity_type text NOT NULL CHECK (entity_type IN ('query_log', 'mapping_upload')),
  entity_id   uuid NOT NULL,
  note        text NOT NULL,
  created_by  text NOT NULL,  -- Clerk user ID
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (entity_type, entity_id)  -- one note per entity
);
```

Migration file: `web/supabase/migrations/YYYYMMDDHHMMSS_admin_notes.sql`

### TypeScript types (added to `lib/types/database.ts`)

```ts
export interface AdminNote {
  id: string
  project_id: string
  entity_type: 'query_log' | 'mapping_upload'
  entity_id: string
  note: string
  created_by: string
  created_at: string
  updated_at: string
}
export type AdminNoteInsert = Omit<AdminNote, 'id' | 'created_at' | 'updated_at'>
export type AdminNoteUpsert = Pick<AdminNote, 'entity_type' | 'entity_id' | 'note' | 'created_by' | 'project_id'>
```

---

## Export for Claude

### Trigger
A single **"Export for Claude"** button in the admin page header (visible on all tabs).

### Client-side generation
`ExportButton` is a `use client` component that receives `projectId` as a prop. On click it calls the `exportIssues(projectId)` server action, receives structured JSON, formats it as markdown in the browser, and triggers a file download as `admin-issues-YYYY-MM-DD.md`.

### Markdown format

```markdown
# Admin Issues Export — Project: [project_code] [project_name]
# Generated: [ISO timestamp]
# Usage: paste this file into Claude Code and ask it to fix the issues below.

## Query Log Issues ([N])

### [QL-1] [response_type] — "[raw_query]"
- raw_query: "[full query text]"
- response_type: [type] | mode: [mode] | execution_ms: [ms]
- logged_at: [ISO timestamp]
- admin_note: "[note text]"
- relevant_files: web/lib/chat/resolver.ts, web/lib/chat/types.ts

### [QL-2] ...

## Mapping Issues ([N])

### [MAP-1] [mapping_type] — [original_filename]
- mapping_type: [financial_type_map | heading_map]
- uploaded_at: [ISO timestamp]
- admin_note: "[note text]"
- relevant_files: web/app/(app)/projects/[projectId]/admin/actions.ts, web/lib/chat/resolver.ts

## Discrepancy Notes ([N])

### [DISC-1] [sheet_name] — [period] — [data_type]
- sheet: [sheet_name] | period: [YYYY-MM] | item_code: [item_code]
- old_value: [old] | new_value: [new]
- review_status: [status]
- reviewer_note: "[note text]"
- relevant_files: web/supabase/migrations/..._initial_schema.sql, web/lib/chat/resolver.ts
```

Notes with no content are omitted from the export. If there are no issues of a given type, that section is omitted.

---

## Files to create / modify

| File | Change |
|---|---|
| `web/supabase/migrations/YYYYMMDD_admin_notes.sql` | New migration — `admin_notes` table |
| `web/lib/types/database.ts` | Add `AdminNote`, `AdminNoteInsert`, `AdminNoteUpsert`; add `admin_notes` to `Database` map |
| `web/app/(app)/projects/[projectId]/admin/page.tsx` | Read `searchParams`, render `AdminTabs` + active tab |
| `web/app/(app)/projects/[projectId]/admin/actions.ts` | Add `getQueryLogs`, `getDiscrepancies`, `reviewDiscrepancy`, `saveAdminNote`, `getAdminNotes`, `exportIssues` |
| `web/components/admin/AdminTabs.tsx` | `use client` tab bar |
| `web/components/admin/QueryLogsTab.tsx` | Server component — filter bar + log table + pagination |
| `web/components/admin/QueryLogRow.tsx` | `use client` — inline note expand |
| `web/components/admin/DiscrepanciesTab.tsx` | Server component — discrepancy table |
| `web/components/admin/DiscrepancyReviewRow.tsx` | `use client` — inline review expand |
| `web/components/admin/ExportButton.tsx` | `use client` — export trigger + MD generation |
| `web/components/mapping-upload-history.tsx` | Add inline note affordance per row |

---

## Out of scope (Phase 12)

- Export/analytics features
- Reviewing already-resolved discrepancies
- Query log deletion
- Reprocessing actions
