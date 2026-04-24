# Phase 11 Admin Panel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a three-tab admin page (Mappings | Query Logs | Discrepancies) with inline discrepancy review, per-row admin notes on query logs and mapping uploads, and an "Export for Claude" download button.

**Architecture:** URL search params drive tab/filter/pagination state on the server-component admin page. Small `use client` islands handle row-level interactivity (note expand, review expand, export trigger). A new `admin_notes` Supabase table stores annotations; `exportIssues` aggregates them into JSON which the client formats into a downloadable `.md` file.

**Tech Stack:** Next.js 16.2 App Router, React 19, TypeScript strict, Supabase JS v2, Clerk v7, Tailwind v4, Vitest (added for pure-function unit tests)

> **Before touching Next.js page files:** read `node_modules/next/dist/docs/` for the current `searchParams`/`params` API — both are `Promise<…>` and must be awaited in Next.js 15+.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `web/supabase/migrations/20260424120000_admin_notes.sql` | Create | `admin_notes` table DDL |
| `web/lib/types/database.ts` | Modify | Add `AdminNote` types + Database entry |
| `web/lib/admin/utils.ts` | Create | `formatPeriod`, `calcPaginationMeta` (pure, tested) |
| `web/lib/admin/export.ts` | Create | `buildExportMarkdown` pure function (tested) |
| `web/lib/admin/__tests__/utils.test.ts` | Create | Unit tests for utils |
| `web/lib/admin/__tests__/export.test.ts` | Create | Unit tests for export |
| `web/app/(app)/projects/[projectId]/admin/actions.ts` | Modify | Add 6 new actions + `resolveProjectUuid` helper |
| `web/app/(app)/projects/[projectId]/admin/page.tsx` | Modify | Read searchParams, render tab system |
| `web/components/admin/AdminTabs.tsx` | Create | `use client` tab bar with Link navigation |
| `web/components/admin/QueryLogsTab.tsx` | Create | Server — filter bar + log table + pagination |
| `web/components/admin/QueryLogsFilterBar.tsx` | Create | `use client` — select filters → router.push |
| `web/components/admin/QueryLogRow.tsx` | Create | `use client` — data row + inline note expand |
| `web/components/admin/DiscrepanciesTab.tsx` | Create | Server — discrepancy table |
| `web/components/admin/DiscrepancyReviewRow.tsx` | Create | `use client` — data row + inline review expand |
| `web/components/admin/ExportButton.tsx` | Create | `use client` — calls exportIssues, triggers download |
| `web/components/admin/InlineNoteRow.tsx` | Create | `use client` — shared reusable expand/collapse note widget |
| `web/components/mapping-upload-history.tsx` | Modify | Add per-row note affordance via InlineNoteRow |
| `web/vitest.config.ts` | Create | Vitest config with `@` alias |
| `web/package.json` | Modify | Add vitest devDep + `test` script |
| `.gitignore` | Modify | Add `.superpowers/` |

---

## Task 1: DB migration

**Files:**
- Create: `web/supabase/migrations/20260424120000_admin_notes.sql`

- [ ] **Step 1: Write the migration**

```sql
-- web/supabase/migrations/20260424120000_admin_notes.sql
CREATE TABLE IF NOT EXISTS admin_notes (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id  uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  entity_type text NOT NULL CHECK (entity_type IN ('query_log', 'mapping_upload')),
  entity_id   uuid NOT NULL,
  note        text NOT NULL,
  created_by  text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (entity_type, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_admin_notes_entity ON admin_notes (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_admin_notes_project ON admin_notes (project_id);
```

- [ ] **Step 2: Apply locally (skip if Supabase CLI not wired up)**

```bash
# If supabase CLI is configured:
cd web && npx supabase db push
# Otherwise apply via Supabase dashboard SQL editor and continue.
```

- [ ] **Step 3: Commit**

```bash
git add web/supabase/migrations/20260424120000_admin_notes.sql
git commit -m "feat(db): add admin_notes table"
```

---

## Task 2: TypeScript types

**Files:**
- Modify: `web/lib/types/database.ts`

- [ ] **Step 1: Add types after the `AdminMappingUploadUpdate` block**

```typescript
// ─────────────────────────────────────────────────────────────
// admin_notes
// ─────────────────────────────────────────────────────────────

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

- [ ] **Step 2: Add to the `Database` Tables map** (after `admin_mapping_uploads` entry)

```typescript
      admin_notes: {
        Row: AdminNote
        Insert: AdminNoteInsert
        Update: Partial<AdminNoteUpsert>
      } & NoRelationships
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd web && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add web/lib/types/database.ts
git commit -m "feat(types): add AdminNote types"
```

---

## Task 3: Vitest setup

**Files:**
- Create: `web/vitest.config.ts`
- Modify: `web/package.json`

- [ ] **Step 1: Install vitest**

```bash
cd web && npm install --save-dev vitest
```

- [ ] **Step 2: Create vitest.config.ts**

```typescript
// web/vitest.config.ts
import { defineConfig } from 'vitest/config'
import path from 'path'

export default defineConfig({
  test: {
    environment: 'node',
    include: ['**/__tests__/**/*.test.ts'],
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, '.'),
    },
  },
})
```

- [ ] **Step 3: Add test script to package.json**

In `"scripts"` add:
```json
"test": "vitest run"
```

- [ ] **Step 4: Run to confirm setup works**

```bash
cd web && npm test
```

Expected: `No test files found` or zero failures (no tests yet).

- [ ] **Step 5: Commit**

```bash
git add web/vitest.config.ts web/package.json
git commit -m "chore: add vitest"
```

---

## Task 4: Admin utility functions (TDD)

**Files:**
- Create: `web/lib/admin/utils.ts`
- Create: `web/lib/admin/__tests__/utils.test.ts`

- [ ] **Step 1: Write the failing tests first**

```typescript
// web/lib/admin/__tests__/utils.test.ts
import { describe, it, expect } from 'vitest'
import { formatPeriod, calcPaginationMeta } from '../utils'

describe('formatPeriod', () => {
  it('formats Jan 2026', () => expect(formatPeriod(1, 2026)).toBe('Jan 2026'))
  it('formats Dec 2025', () => expect(formatPeriod(12, 2025)).toBe('Dec 2025'))
  it('formats Feb 2026', () => expect(formatPeriod(2, 2026)).toBe('Feb 2026'))
})

describe('calcPaginationMeta', () => {
  it('calculates first page of 143 items at page size 20', () => {
    expect(calcPaginationMeta(143, 1, 20)).toEqual({
      totalPages: 8,
      from: 1,
      to: 20,
      hasPrev: false,
      hasNext: true,
    })
  })
  it('calculates last page', () => {
    expect(calcPaginationMeta(143, 8, 20)).toEqual({
      totalPages: 8,
      from: 141,
      to: 143,
      hasPrev: true,
      hasNext: false,
    })
  })
  it('single page of 5', () => {
    expect(calcPaginationMeta(5, 1, 20)).toEqual({
      totalPages: 1,
      from: 1,
      to: 5,
      hasPrev: false,
      hasNext: false,
    })
  })
  it('zero items', () => {
    expect(calcPaginationMeta(0, 1, 20)).toEqual({
      totalPages: 0,
      from: 0,
      to: 0,
      hasPrev: false,
      hasNext: false,
    })
  })
})
```

- [ ] **Step 2: Run — verify tests fail**

```bash
cd web && npm test
```

Expected: FAIL — `Cannot find module '../utils'`

- [ ] **Step 3: Implement utils.ts**

```typescript
// web/lib/admin/utils.ts
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

export function formatPeriod(month: number, year: number): string {
  return `${MONTHS[month - 1]} ${year}`
}

export interface PaginationMeta {
  totalPages: number
  from: number
  to: number
  hasPrev: boolean
  hasNext: boolean
}

export function calcPaginationMeta(total: number, page: number, pageSize: number): PaginationMeta {
  if (total === 0) return { totalPages: 0, from: 0, to: 0, hasPrev: false, hasNext: false }
  const totalPages = Math.ceil(total / pageSize)
  const from = (page - 1) * pageSize + 1
  const to = Math.min(page * pageSize, total)
  return { totalPages, from, to, hasPrev: page > 1, hasNext: page < totalPages }
}
```

- [ ] **Step 4: Run — verify tests pass**

```bash
cd web && npm test
```

Expected: 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add web/lib/admin/utils.ts web/lib/admin/__tests__/utils.test.ts
git commit -m "feat(admin): add formatPeriod + calcPaginationMeta utils"
```

---

## Task 5: Export markdown helper (TDD)

**Files:**
- Create: `web/lib/admin/export.ts`
- Create: `web/lib/admin/__tests__/export.test.ts`

- [ ] **Step 1: Write the failing tests**

```typescript
// web/lib/admin/__tests__/export.test.ts
import { describe, it, expect } from 'vitest'
import { buildExportMarkdown, type ExportData } from '../export'

const BASE: ExportData = {
  projectCode: 'PROJ-001',
  projectName: 'Northshore',
  generatedAt: '2026-04-24T09:00:00.000Z',
  queryLogIssues: [],
  mappingIssues: [],
  discrepancyNotes: [],
}

describe('buildExportMarkdown', () => {
  it('includes header with project info', () => {
    const md = buildExportMarkdown(BASE)
    expect(md).toContain('PROJ-001 Northshore')
    expect(md).toContain('2026-04-24T09:00:00.000Z')
    expect(md).toContain('paste this file into Claude Code')
  })

  it('omits empty sections', () => {
    const md = buildExportMarkdown(BASE)
    expect(md).not.toContain('## Query Log Issues')
    expect(md).not.toContain('## Mapping Issues')
    expect(md).not.toContain('## Discrepancy Notes')
  })

  it('renders a query log issue', () => {
    const data: ExportData = {
      ...BASE,
      queryLogIssues: [{
        index: 1,
        rawQuery: 'labour cost',
        responseType: 'ambiguity',
        mode: 'standard',
        executionMs: 67,
        loggedAt: '2026-04-22T08:55:00.000Z',
        adminNote: 'alias missing from heading_map',
      }],
    }
    const md = buildExportMarkdown(data)
    expect(md).toContain('## Query Log Issues (1)')
    expect(md).toContain('[QL-1] ambiguity — "labour cost"')
    expect(md).toContain('alias missing from heading_map')
    expect(md).toContain('web/lib/chat/resolver.ts')
  })

  it('renders a mapping issue', () => {
    const data: ExportData = {
      ...BASE,
      mappingIssues: [{
        index: 1,
        mappingType: 'financial_type_map',
        filename: 'ftm_2026.csv',
        uploadedAt: '2026-04-20T14:00:00.000Z',
        adminNote: 'Prelims not matching',
      }],
    }
    const md = buildExportMarkdown(data)
    expect(md).toContain('## Mapping Issues (1)')
    expect(md).toContain('[MAP-1] financial_type_map — ftm_2026.csv')
    expect(md).toContain('Prelims not matching')
  })

  it('renders a discrepancy note', () => {
    const data: ExportData = {
      ...BASE,
      discrepancyNotes: [{
        index: 1,
        sheetName: 'P&L',
        period: '2026-02',
        dataType: 'Labour Cost',
        itemCode: 'LC-001',
        oldValue: 12400,
        newValue: 13100,
        reviewStatus: 'pending',
        reviewerNote: 'genuine data change',
      }],
    }
    const md = buildExportMarkdown(data)
    expect(md).toContain('## Discrepancy Notes (1)')
    expect(md).toContain('[DISC-1] P&L — 2026-02 — Labour Cost')
    expect(md).toContain('genuine data change')
  })
})
```

- [ ] **Step 2: Run — verify tests fail**

```bash
cd web && npm test
```

Expected: FAIL — `Cannot find module '../export'`

- [ ] **Step 3: Implement export.ts**

```typescript
// web/lib/admin/export.ts

export interface QueryLogIssue {
  index: number
  rawQuery: string
  responseType: string | null
  mode: string
  executionMs: number | null
  loggedAt: string
  adminNote: string
}

export interface MappingIssue {
  index: number
  mappingType: string
  filename: string
  uploadedAt: string
  adminNote: string
}

export interface DiscrepancyNote {
  index: number
  sheetName: string
  period: string
  dataType: string | null
  itemCode: string | null
  oldValue: number | null
  newValue: number | null
  reviewStatus: string
  reviewerNote: string
}

export interface ExportData {
  projectCode: string
  projectName: string
  generatedAt: string
  queryLogIssues: QueryLogIssue[]
  mappingIssues: MappingIssue[]
  discrepancyNotes: DiscrepancyNote[]
}

export function buildExportMarkdown(data: ExportData): string {
  const lines: string[] = [
    `# Admin Issues Export — Project: ${data.projectCode} ${data.projectName}`,
    `# Generated: ${data.generatedAt}`,
    `# Usage: paste this file into Claude Code and ask it to fix the issues below.`,
  ]

  if (data.queryLogIssues.length > 0) {
    lines.push('', `## Query Log Issues (${data.queryLogIssues.length})`)
    for (const q of data.queryLogIssues) {
      lines.push(
        '',
        `### [QL-${q.index}] ${q.responseType ?? 'unknown'} — "${q.rawQuery}"`,
        `- raw_query: "${q.rawQuery}"`,
        `- response_type: ${q.responseType ?? 'null'} | mode: ${q.mode} | execution_ms: ${q.executionMs ?? 'null'}`,
        `- logged_at: ${q.loggedAt}`,
        `- admin_note: "${q.adminNote}"`,
        `- relevant_files: web/lib/chat/resolver.ts, web/lib/chat/types.ts`,
      )
    }
  }

  if (data.mappingIssues.length > 0) {
    lines.push('', `## Mapping Issues (${data.mappingIssues.length})`)
    for (const m of data.mappingIssues) {
      lines.push(
        '',
        `### [MAP-${m.index}] ${m.mappingType} — ${m.filename}`,
        `- mapping_type: ${m.mappingType}`,
        `- uploaded_at: ${m.uploadedAt}`,
        `- admin_note: "${m.adminNote}"`,
        `- relevant_files: web/app/(app)/projects/[projectId]/admin/actions.ts, web/lib/chat/resolver.ts`,
      )
    }
  }

  if (data.discrepancyNotes.length > 0) {
    lines.push('', `## Discrepancy Notes (${data.discrepancyNotes.length})`)
    for (const d of data.discrepancyNotes) {
      lines.push(
        '',
        `### [DISC-${d.index}] ${d.sheetName} — ${d.period} — ${d.dataType ?? d.itemCode ?? 'unknown'}`,
        `- sheet: ${d.sheetName} | period: ${d.period} | item_code: ${d.itemCode ?? 'null'}`,
        `- old_value: ${d.oldValue ?? 'null'} | new_value: ${d.newValue ?? 'null'}`,
        `- review_status: ${d.reviewStatus}`,
        `- reviewer_note: "${d.reviewerNote}"`,
        `- relevant_files: web/supabase/migrations/20260421000001_initial_schema.sql, web/lib/chat/resolver.ts`,
      )
    }
  }

  return lines.join('\n')
}
```

- [ ] **Step 4: Run — verify all tests pass**

```bash
cd web && npm test
```

Expected: 11 tests pass (7 from utils + 4 from export).

- [ ] **Step 5: Commit**

```bash
git add web/lib/admin/export.ts web/lib/admin/__tests__/export.test.ts
git commit -m "feat(admin): add buildExportMarkdown helper"
```

---

## Task 6: Server actions — read

**Files:**
- Modify: `web/app/(app)/projects/[projectId]/admin/actions.ts`

- [ ] **Step 1: Add imports and the `resolveProjectUuid` helper at the top of the file (after existing imports)**

```typescript
import type {
  AdminMappingUpload,
  MappingType,
  QueryLog,
  Discrepancy,
  AdminNote,
  AdminNoteUpsert,
  QueryMode,
  ResponseType,
} from '@/lib/types/database'
```

Replace the existing import line:
```typescript
import type { AdminMappingUpload, MappingType } from '@/lib/types/database'
```

Then add the helper after the imports:

```typescript
async function resolveProjectUuid(
  supabase: ReturnType<typeof createServerSupabase>,
  projectCode: string
): Promise<string | null> {
  const { data } = await supabase
    .from('projects')
    .select('id')
    .eq('project_code', projectCode)
    .single()
  return data?.id ?? null
}
```

- [ ] **Step 2: Add `getQueryLogs` at the end of actions.ts**

```typescript
export interface QueryLogFilters {
  mode?: QueryMode
  type?: ResponseType
}

export interface PaginatedQueryLogs {
  logs: QueryLog[]
  total: number
}

export async function getQueryLogs(
  projectCode: string,
  filters: QueryLogFilters,
  page: number
): Promise<PaginatedQueryLogs> {
  const PAGE_SIZE = 20
  let supabase: ReturnType<typeof createServerSupabase>
  try { supabase = createServerSupabase() } catch { return { logs: [], total: 0 } }

  const projectId = await resolveProjectUuid(supabase, projectCode)
  if (!projectId) return { logs: [], total: 0 }

  let query = supabase
    .from('query_logs')
    .select('*', { count: 'exact' })
    .eq('project_id', projectId)
    .order('created_at', { ascending: false })
    .range((page - 1) * PAGE_SIZE, page * PAGE_SIZE - 1)

  if (filters.mode) query = query.eq('mode', filters.mode)
  if (filters.type) query = query.eq('response_type', filters.type)

  const { data, count } = await query
  return { logs: (data ?? []) as QueryLog[], total: count ?? 0 }
}
```

- [ ] **Step 3: Add `getDiscrepancies`**

```typescript
export async function getDiscrepancies(projectCode: string): Promise<Discrepancy[]> {
  let supabase: ReturnType<typeof createServerSupabase>
  try { supabase = createServerSupabase() } catch { return [] }

  const projectId = await resolveProjectUuid(supabase, projectCode)
  if (!projectId) return []

  const { data } = await supabase
    .from('discrepancies')
    .select('*')
    .eq('project_id', projectId)
    .eq('review_status', 'pending')
    .order('detected_at', { ascending: false })

  return (data ?? []) as Discrepancy[]
}
```

- [ ] **Step 4: Add `getAdminNotes`**

```typescript
export async function getAdminNotes(
  entityIds: string[]
): Promise<Record<string, AdminNote>> {
  if (entityIds.length === 0) return {}
  let supabase: ReturnType<typeof createServerSupabase>
  try { supabase = createServerSupabase() } catch { return {} }

  const { data } = await supabase
    .from('admin_notes')
    .select('*')
    .in('entity_id', entityIds)

  const result: Record<string, AdminNote> = {}
  for (const note of (data ?? []) as AdminNote[]) {
    result[note.entity_id] = note
  }
  return result
}
```

- [ ] **Step 5: Verify TypeScript compiles**

```bash
cd web && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add web/app/\(app\)/projects/\[projectId\]/admin/actions.ts
git commit -m "feat(admin): add getQueryLogs, getDiscrepancies, getAdminNotes"
```

---

## Task 7: Server actions — write

**Files:**
- Modify: `web/app/(app)/projects/[projectId]/admin/actions.ts`

- [ ] **Step 1: Add `reviewDiscrepancy`**

```typescript
export async function reviewDiscrepancy(
  discrepancyId: string,
  status: 'reviewed' | 'dismissed',
  note: string,
  projectCode: string
): Promise<{ error: string | null }> {
  const { userId } = await auth()
  if (!userId) return { error: 'Unauthorized' }

  let supabase: ReturnType<typeof createServerSupabase>
  try { supabase = createServerSupabase() } catch { return { error: 'Supabase not configured' } }

  const { error } = await supabase
    .from('discrepancies')
    .update({
      review_status: status,
      reviewer_note: note.trim() || null,
      reviewed_by: userId,
      reviewed_at: new Date().toISOString(),
    })
    .eq('id', discrepancyId)

  if (error) return { error: error.message }
  revalidatePath(`/projects/${projectCode}/admin`)
  return { error: null }
}
```

- [ ] **Step 2: Add `saveAdminNote`**

```typescript
export async function saveAdminNote(
  entityType: 'query_log' | 'mapping_upload',
  entityId: string,
  projectCode: string,
  note: string
): Promise<{ error: string | null }> {
  const { userId } = await auth()
  if (!userId) return { error: 'Unauthorized' }

  let supabase: ReturnType<typeof createServerSupabase>
  try { supabase = createServerSupabase() } catch { return { error: 'Supabase not configured' } }

  const projectId = await resolveProjectUuid(supabase, projectCode)
  if (!projectId) return { error: 'Project not found' }

  const upsertData: AdminNoteUpsert = {
    entity_type: entityType,
    entity_id: entityId,
    project_id: projectId,
    note: note.trim(),
    created_by: userId,
  }

  const { error } = await supabase
    .from('admin_notes')
    .upsert(upsertData, { onConflict: 'entity_type,entity_id' })

  if (error) return { error: error.message }
  revalidatePath(`/projects/${projectCode}/admin`)
  return { error: null }
}
```

- [ ] **Step 3: Add `exportIssues`**

```typescript
import type { ExportData, QueryLogIssue, MappingIssue, DiscrepancyNote } from '@/lib/admin/export'

export async function exportIssues(projectCode: string): Promise<ExportData | null> {
  let supabase: ReturnType<typeof createServerSupabase>
  try { supabase = createServerSupabase() } catch { return null }

  const projectId = await resolveProjectUuid(supabase, projectCode)
  if (!projectId) return null

  const { data: project } = await supabase
    .from('projects')
    .select('project_code, project_name')
    .eq('id', projectId)
    .single()

  const [notesResult, discResult] = await Promise.all([
    supabase
      .from('admin_notes')
      .select('*, query_logs!inner(raw_query, response_type, mode, execution_ms, created_at), admin_mapping_uploads!inner(original_filename, mapping_type, created_at)')
      .eq('project_id', projectId),
    supabase
      .from('discrepancies')
      .select('*')
      .eq('project_id', projectId)
      .not('reviewer_note', 'is', null),
  ])

  // Build separate note lists from admin_notes rows
  const queryLogIssues: QueryLogIssue[] = []
  const mappingIssues: MappingIssue[] = []

  for (const n of ((notesResult.data ?? []) as (AdminNote & { query_logs?: QueryLog; admin_mapping_uploads?: AdminMappingUpload })[]) ) {
    if (n.entity_type === 'query_log' && n.query_logs) {
      queryLogIssues.push({
        index: queryLogIssues.length + 1,
        rawQuery: n.query_logs.raw_query,
        responseType: n.query_logs.response_type,
        mode: n.query_logs.mode,
        executionMs: n.query_logs.execution_ms,
        loggedAt: n.query_logs.created_at,
        adminNote: n.note,
      })
    } else if (n.entity_type === 'mapping_upload' && n.admin_mapping_uploads) {
      mappingIssues.push({
        index: mappingIssues.length + 1,
        mappingType: n.admin_mapping_uploads.mapping_type,
        filename: n.admin_mapping_uploads.original_filename,
        uploadedAt: n.admin_mapping_uploads.created_at,
        adminNote: n.note,
      })
    }
  }

  const discrepancyNotes: DiscrepancyNote[] = ((discResult.data ?? []) as Discrepancy[])
    .filter(d => d.reviewer_note)
    .map((d, i) => ({
      index: i + 1,
      sheetName: d.sheet_name,
      period: `${d.report_year}-${String(d.report_month).padStart(2, '0')}`,
      dataType: d.data_type,
      itemCode: d.item_code,
      oldValue: d.old_value,
      newValue: d.new_value,
      reviewStatus: d.review_status,
      reviewerNote: d.reviewer_note!,
    }))

  return {
    projectCode: project?.project_code ?? projectCode,
    projectName: project?.project_name ?? '',
    generatedAt: new Date().toISOString(),
    queryLogIssues,
    mappingIssues,
    discrepancyNotes,
  }
}
```

> **Note on the join query:** Supabase JS `select` with `!inner` join syntax requires the tables to have foreign keys defined in the schema. If those FK relationships aren't present, replace the joined query with two separate queries — fetch all `admin_notes` for the project, then batch-fetch the referenced entities by their IDs.

- [ ] **Step 4: Add `ExportData` import and verify TypeScript**

The `exportIssues` function imports from `@/lib/admin/export`. Make sure that import is at the top of actions.ts:

```typescript
import type { ExportData, QueryLogIssue, MappingIssue, DiscrepancyNote } from '@/lib/admin/export'
```

```bash
cd web && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add web/app/\(app\)/projects/\[projectId\]/admin/actions.ts
git commit -m "feat(admin): add reviewDiscrepancy, saveAdminNote, exportIssues actions"
```

---

## Task 8: AdminTabs component

**Files:**
- Create: `web/components/admin/AdminTabs.tsx`

- [ ] **Step 1: Create the component**

```typescript
// web/components/admin/AdminTabs.tsx
'use client'

import Link from 'next/link'
import { usePathname, useSearchParams } from 'next/navigation'

export type AdminTab = 'mappings' | 'query-logs' | 'discrepancies'

const TABS: { label: string; value: AdminTab }[] = [
  { label: 'Mappings', value: 'mappings' },
  { label: 'Query Logs', value: 'query-logs' },
  { label: 'Discrepancies', value: 'discrepancies' },
]

interface AdminTabsProps {
  projectId: string
  activeTab: AdminTab
}

export function AdminTabs({ projectId, activeTab }: AdminTabsProps) {
  return (
    <div className="flex border-b border-zinc-200 bg-white px-4">
      {TABS.map((tab) => {
        const href = `/projects/${projectId}/admin?tab=${tab.value}`
        const isActive = activeTab === tab.value
        return (
          <Link
            key={tab.value}
            href={href}
            className={`border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
              isActive
                ? 'border-zinc-900 text-zinc-900'
                : 'border-transparent text-zinc-500 hover:text-zinc-700'
            }`}
          >
            {tab.label}
          </Link>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd web && npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add web/components/admin/AdminTabs.tsx
git commit -m "feat(admin): add AdminTabs component"
```

---

## Task 9: InlineNoteRow shared component

**Files:**
- Create: `web/components/admin/InlineNoteRow.tsx`

This component renders as two table rows: the trigger cell content (inline, not a full row) and an expansion row. Callers embed the trigger in their own row and conditionally render the expansion.

Since a `<tr>` can't be conditionally wrapped, `InlineNoteRow` is split into two exported pieces: `NoteCell` (rendered inside the caller's `<td>`) and `NoteExpandRow` (rendered as a sibling `<tr>`).

- [ ] **Step 1: Create the component**

```typescript
// web/components/admin/InlineNoteRow.tsx
'use client'

import { useState, useTransition } from 'react'

interface NoteProps {
  existingNote: string | null
  onSave: (note: string) => Promise<{ error: string | null }>
  colSpan: number
}

interface NoteCellProps {
  hasNote: boolean
  isOpen: boolean
  onToggle: () => void
}

export function NoteCell({ hasNote, isOpen, onToggle }: NoteCellProps) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="text-xs text-zinc-400 hover:text-zinc-700 transition-colors"
    >
      {isOpen ? 'Cancel' : hasNote ? '📝 Edit note' : '+ Note'}
    </button>
  )
}

export function NoteExpandRow({
  existingNote,
  onSave,
  colSpan,
  onClose,
}: NoteProps & { onClose: () => void }) {
  const [text, setText] = useState(existingNote ?? '')
  const [isPending, startTransition] = useTransition()
  const [error, setError] = useState<string | null>(null)

  function handleSave() {
    startTransition(async () => {
      const result = await onSave(text)
      if (result.error) {
        setError(result.error)
      } else {
        onClose()
      }
    })
  }

  return (
    <tr className="bg-amber-50">
      <td colSpan={colSpan} className="px-3 py-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          placeholder="Note for Claude Code (e.g. 'query returned wrong type — should resolve to shortcut 3')"
          className="w-full resize-none rounded border border-amber-200 bg-white px-2 py-1.5 text-xs text-zinc-800 placeholder:text-zinc-400 focus:border-amber-400 focus:outline-none"
        />
        {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
        <div className="mt-1.5 flex gap-2">
          <button
            type="button"
            onClick={handleSave}
            disabled={isPending || !text.trim()}
            className="rounded bg-zinc-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
          >
            {isPending ? 'Saving…' : 'Save note'}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-zinc-200 bg-white px-3 py-1 text-xs text-zinc-600"
          >
            Cancel
          </button>
        </div>
      </td>
    </tr>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd web && npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add web/components/admin/InlineNoteRow.tsx
git commit -m "feat(admin): add InlineNoteRow shared component"
```

---

## Task 10: QueryLogsFilterBar

**Files:**
- Create: `web/components/admin/QueryLogsFilterBar.tsx`

- [ ] **Step 1: Create the component**

```typescript
// web/components/admin/QueryLogsFilterBar.tsx
'use client'

import { useRouter, usePathname, useSearchParams } from 'next/navigation'
import type { QueryMode, ResponseType } from '@/lib/types/database'

const RESPONSE_TYPES: ResponseType[] = [
  'value','table','trend','compare','total','detail',
  'risk','cash_flow','list','ambiguity','missing','error',
]

interface QueryLogsFilterBarProps {
  mode: QueryMode | null
  type: ResponseType | null
  from: number
  to: number
  total: number
}

export function QueryLogsFilterBar({ mode, type, from, to, total }: QueryLogsFilterBarProps) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  const update = (key: string, value: string) => {
    const params = new URLSearchParams(searchParams.toString())
    if (value) params.set(key, value)
    else params.delete(key)
    params.delete('page')
    router.push(`${pathname}?${params.toString()}`)
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="flex items-center gap-2">
        <label className="text-xs text-zinc-500">Mode</label>
        <select
          value={mode ?? ''}
          onChange={(e) => update('mode', e.target.value)}
          className="rounded border border-zinc-200 bg-white px-2 py-1 text-xs text-zinc-700"
        >
          <option value="">All modes</option>
          <option value="standard">standard</option>
          <option value="verbose">verbose</option>
        </select>
      </div>
      <div className="flex items-center gap-2">
        <label className="text-xs text-zinc-500">Type</label>
        <select
          value={type ?? ''}
          onChange={(e) => update('type', e.target.value)}
          className="rounded border border-zinc-200 bg-white px-2 py-1 text-xs text-zinc-700"
        >
          <option value="">All types</option>
          {RESPONSE_TYPES.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </div>
      {total > 0 && (
        <span className="ml-auto text-xs text-zinc-400">
          Showing {from}–{to} of {total}
        </span>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd web && npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add web/components/admin/QueryLogsFilterBar.tsx
git commit -m "feat(admin): add QueryLogsFilterBar component"
```

---

## Task 11: QueryLogsTab + QueryLogRow

**Files:**
- Create: `web/components/admin/QueryLogRow.tsx`
- Create: `web/components/admin/QueryLogsTab.tsx`

- [ ] **Step 1: Create QueryLogRow**

```typescript
// web/components/admin/QueryLogRow.tsx
'use client'

import { useState } from 'react'
import { NoteCell, NoteExpandRow } from './InlineNoteRow'
import type { QueryLog, AdminNote } from '@/lib/types/database'

const TYPE_COLORS: Record<string, string> = {
  value:     'bg-blue-100 text-blue-700',
  table:     'bg-green-100 text-green-700',
  trend:     'bg-purple-100 text-purple-700',
  compare:   'bg-indigo-100 text-indigo-700',
  total:     'bg-teal-100 text-teal-700',
  ambiguity: 'bg-yellow-100 text-yellow-700',
  missing:   'bg-orange-100 text-orange-700',
  error:     'bg-red-100 text-red-700',
}

function formatTs(ts: string) {
  return new Date(ts).toLocaleString('en-GB', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  })
}

interface QueryLogRowProps {
  log: QueryLog
  note: AdminNote | null
  projectId: string
  onSave: (logId: string, note: string) => Promise<{ error: string | null }>
}

export function QueryLogRow({ log, note, projectId, onSave }: QueryLogRowProps) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <>
      <tr className="border-b border-zinc-100 hover:bg-zinc-50">
        <td className="max-w-[280px] px-3 py-2.5">
          <span
            className="block truncate text-xs text-zinc-800"
            title={log.raw_query}
          >
            {log.raw_query}
          </span>
        </td>
        <td className="px-3 py-2.5">
          {log.response_type && (
            <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${TYPE_COLORS[log.response_type] ?? 'bg-zinc-100 text-zinc-600'}`}>
              {log.response_type}
            </span>
          )}
        </td>
        <td className="px-3 py-2.5 text-xs text-zinc-500">{log.mode}</td>
        <td className="px-3 py-2.5 text-xs tabular-nums text-zinc-500">
          {log.execution_ms ?? '—'}
        </td>
        <td className="px-3 py-2.5 text-xs text-zinc-400">{formatTs(log.created_at)}</td>
        <td className="px-3 py-2.5">
          <NoteCell
            hasNote={!!note}
            isOpen={isOpen}
            onToggle={() => setIsOpen((v) => !v)}
          />
        </td>
      </tr>
      {isOpen && (
        <NoteExpandRow
          existingNote={note?.note ?? null}
          onSave={(text) => onSave(log.id, text)}
          colSpan={6}
          onClose={() => setIsOpen(false)}
        />
      )}
    </>
  )
}
```

- [ ] **Step 2: Create QueryLogsTab**

```typescript
// web/components/admin/QueryLogsTab.tsx
import Link from 'next/link'
import { QueryLogRow } from './QueryLogRow'
import { QueryLogsFilterBar } from './QueryLogsFilterBar'
import { saveAdminNote } from '@/app/(app)/projects/[projectId]/admin/actions'
import { calcPaginationMeta } from '@/lib/admin/utils'
import type { QueryLog, AdminNote, QueryMode, ResponseType } from '@/lib/types/database'

interface QueryLogsTabProps {
  projectId: string
  logs: QueryLog[]
  notes: Record<string, AdminNote>
  total: number
  page: number
  mode: QueryMode | null
  type: ResponseType | null
}

export function QueryLogsTab({
  projectId, logs, notes, total, page, mode, type,
}: QueryLogsTabProps) {
  const PAGE_SIZE = 20
  const meta = calcPaginationMeta(total, page, PAGE_SIZE)

  const buildPageHref = (p: number) => {
    const params = new URLSearchParams({ tab: 'query-logs', page: String(p) })
    if (mode) params.set('mode', mode)
    if (type) params.set('type', type)
    return `/projects/${projectId}/admin?${params.toString()}`
  }

  const saveNote = saveAdminNote.bind(null, 'query_log')

  return (
    <div className="space-y-4">
      <QueryLogsFilterBar
        mode={mode}
        type={type}
        from={meta.from}
        to={meta.to}
        total={total}
      />

      {logs.length === 0 ? (
        <p className="py-8 text-center text-xs text-zinc-400">No query logs found.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-zinc-200 text-left text-xs font-medium text-zinc-400">
                <th className="px-3 py-2.5">Query</th>
                <th className="px-3 py-2.5">Type</th>
                <th className="px-3 py-2.5">Mode</th>
                <th className="px-3 py-2.5">ms</th>
                <th className="px-3 py-2.5">When</th>
                <th className="px-3 py-2.5">Note</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => (
                <QueryLogRow
                  key={log.id}
                  log={log}
                  note={notes[log.id] ?? null}
                  projectId={projectId}
                  onSave={(logId, note) => saveNote(logId, projectId, note)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {meta.totalPages > 1 && (
        <div className="flex items-center justify-end gap-1">
          {meta.hasPrev && (
            <Link href={buildPageHref(page - 1)} className="rounded border border-zinc-200 bg-white px-3 py-1 text-xs text-zinc-600 hover:bg-zinc-50">
              ← Prev
            </Link>
          )}
          {Array.from({ length: meta.totalPages }, (_, i) => i + 1)
            .filter((p) => Math.abs(p - page) <= 2)
            .map((p) => (
              <Link
                key={p}
                href={buildPageHref(p)}
                className={`rounded border px-3 py-1 text-xs ${
                  p === page
                    ? 'border-zinc-900 bg-zinc-900 text-white'
                    : 'border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-50'
                }`}
              >
                {p}
              </Link>
            ))}
          {meta.hasNext && (
            <Link href={buildPageHref(page + 1)} className="rounded border border-zinc-200 bg-white px-3 py-1 text-xs text-zinc-600 hover:bg-zinc-50">
              Next →
            </Link>
          )}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Verify TypeScript**

```bash
cd web && npx tsc --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add web/components/admin/QueryLogRow.tsx web/components/admin/QueryLogsTab.tsx
git commit -m "feat(admin): add QueryLogRow and QueryLogsTab"
```

---

## Task 12: DiscrepanciesTab + DiscrepancyReviewRow

**Files:**
- Create: `web/components/admin/DiscrepancyReviewRow.tsx`
- Create: `web/components/admin/DiscrepanciesTab.tsx`

- [ ] **Step 1: Create DiscrepancyReviewRow**

```typescript
// web/components/admin/DiscrepancyReviewRow.tsx
'use client'

import { useState, useTransition } from 'react'
import type { Discrepancy } from '@/lib/types/database'
import { formatPeriod } from '@/lib/admin/utils'

type ReviewAction = 'reviewed' | 'dismissed'

interface DiscrepancyReviewRowProps {
  discrepancy: Discrepancy
  onReview: (id: string, status: ReviewAction, note: string) => Promise<{ error: string | null }>
}

function formatValue(v: number | null) {
  if (v === null) return '—'
  return new Intl.NumberFormat('en-AU', { style: 'currency', currency: 'AUD', maximumFractionDigits: 0 }).format(v)
}

export function DiscrepancyReviewRow({ discrepancy: d, onReview }: DiscrepancyReviewRowProps) {
  const [action, setAction] = useState<ReviewAction | null>(null)
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()

  function open(a: ReviewAction) {
    setAction(a)
    setNote('')
    setError(null)
  }

  function close() {
    setAction(null)
    setError(null)
  }

  function confirm() {
    if (!action) return
    startTransition(async () => {
      const result = await onReview(d.id, action, note)
      if (result.error) setError(result.error)
    })
  }

  return (
    <>
      <tr className="border-b border-zinc-100 hover:bg-zinc-50">
        <td className="px-3 py-2.5 text-xs text-zinc-800">{d.sheet_name}</td>
        <td className="px-3 py-2.5 text-xs text-zinc-600">
          {formatPeriod(d.report_month, d.report_year)}
        </td>
        <td className="px-3 py-2.5 text-xs text-zinc-500">
          {d.data_type ?? d.item_code ?? '—'}
        </td>
        <td className="px-3 py-2.5 text-xs font-medium text-red-600 tabular-nums">
          {formatValue(d.old_value)}
        </td>
        <td className="px-3 py-2.5 text-xs font-medium text-green-600 tabular-nums">
          {formatValue(d.new_value)}
        </td>
        <td className="px-3 py-2.5">
          {action ? (
            <span className="text-xs font-medium text-zinc-400">
              ▼ {action === 'reviewed' ? 'Reviewing…' : 'Dismissing…'}
            </span>
          ) : (
            <span className="flex gap-2">
              <button
                type="button"
                onClick={() => open('reviewed')}
                className="text-xs text-blue-600 hover:text-blue-800"
              >
                Review
              </button>
              <span className="text-zinc-300">·</span>
              <button
                type="button"
                onClick={() => open('dismissed')}
                className="text-xs text-zinc-400 hover:text-zinc-600"
              >
                Dismiss
              </button>
            </span>
          )}
        </td>
      </tr>
      {action && (
        <tr className="border-b border-zinc-100 bg-blue-50">
          <td colSpan={6} className="px-3 py-2">
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              placeholder="Optional note (e.g. confirmed correct after supplier invoice)…"
              className="w-full resize-none rounded border border-blue-200 bg-white px-2 py-1.5 text-xs text-zinc-800 placeholder:text-zinc-400 focus:border-blue-400 focus:outline-none"
            />
            {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
            <div className="mt-1.5 flex gap-2">
              <button
                type="button"
                onClick={confirm}
                disabled={isPending}
                className="rounded bg-zinc-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
              >
                {isPending ? 'Saving…' : action === 'reviewed' ? 'Mark reviewed' : 'Dismiss'}
              </button>
              <button
                type="button"
                onClick={close}
                className="rounded border border-zinc-200 bg-white px-3 py-1 text-xs text-zinc-600"
              >
                Cancel
              </button>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}
```

- [ ] **Step 2: Create DiscrepanciesTab**

```typescript
// web/components/admin/DiscrepanciesTab.tsx
import { DiscrepancyReviewRow } from './DiscrepancyReviewRow'
import { reviewDiscrepancy } from '@/app/(app)/projects/[projectId]/admin/actions'
import type { Discrepancy } from '@/lib/types/database'

interface DiscrepanciesTabProps {
  discrepancies: Discrepancy[]
  projectId: string
}

export function DiscrepanciesTab({ discrepancies, projectId }: DiscrepanciesTabProps) {
  const handleReview = reviewDiscrepancy.bind(null)

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-zinc-700">
          {discrepancies.length === 0
            ? 'No open discrepancies'
            : `${discrepancies.length} open discrepanc${discrepancies.length === 1 ? 'y' : 'ies'}`}
        </p>
        <p className="text-xs text-zinc-400">Showing pending only</p>
      </div>

      {discrepancies.length === 0 ? (
        <div className="rounded-lg border border-zinc-200 bg-white py-10 text-center">
          <p className="text-sm text-zinc-400">All discrepancies have been reviewed.</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-zinc-200 text-left text-xs font-medium text-zinc-400">
                <th className="px-3 py-2.5">Sheet</th>
                <th className="px-3 py-2.5">Period</th>
                <th className="px-3 py-2.5">Item</th>
                <th className="px-3 py-2.5">Old value</th>
                <th className="px-3 py-2.5">New value</th>
                <th className="px-3 py-2.5">Actions</th>
              </tr>
            </thead>
            <tbody>
              {discrepancies.map((d) => (
                <DiscrepancyReviewRow
                  key={d.id}
                  discrepancy={d}
                  onReview={(id, status, note) =>
                    handleReview(id, status, note, projectId)
                  }
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Verify TypeScript**

```bash
cd web && npx tsc --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add web/components/admin/DiscrepancyReviewRow.tsx web/components/admin/DiscrepanciesTab.tsx
git commit -m "feat(admin): add DiscrepancyReviewRow and DiscrepanciesTab"
```

---

## Task 13: ExportButton

**Files:**
- Create: `web/components/admin/ExportButton.tsx`

- [ ] **Step 1: Create the component**

```typescript
// web/components/admin/ExportButton.tsx
'use client'

import { useState, useTransition } from 'react'
import { exportIssues } from '@/app/(app)/projects/[projectId]/admin/actions'
import { buildExportMarkdown } from '@/lib/admin/export'

interface ExportButtonProps {
  projectId: string
}

export function ExportButton({ projectId }: ExportButtonProps) {
  const [isPending, startTransition] = useTransition()
  const [error, setError] = useState<string | null>(null)

  function handleExport() {
    setError(null)
    startTransition(async () => {
      const data = await exportIssues(projectId)
      if (!data) {
        setError('Export failed — project not found.')
        return
      }
      const md = buildExportMarkdown(data)
      const blob = new Blob([md], { type: 'text/markdown' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      const date = new Date().toISOString().slice(0, 10)
      a.href = url
      a.download = `admin-issues-${date}.md`
      a.click()
      URL.revokeObjectURL(url)
    })
  }

  return (
    <div>
      <button
        type="button"
        onClick={handleExport}
        disabled={isPending}
        className="rounded border border-zinc-200 bg-white px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"
      >
        {isPending ? 'Exporting…' : 'Export for Claude'}
      </button>
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd web && npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add web/components/admin/ExportButton.tsx
git commit -m "feat(admin): add ExportButton component"
```

---

## Task 14: MappingUploadHistory notes

**Files:**
- Modify: `web/components/mapping-upload-history.tsx`

- [ ] **Step 1: Update the component to accept notes and an onSave callback**

Replace the entire file:

```typescript
// web/components/mapping-upload-history.tsx
'use client'

import { useState } from 'react'
import { NoteCell, NoteExpandRow } from './admin/InlineNoteRow'
import type { AdminMappingUpload, AdminNote } from '@/lib/types/database'

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    pending: 'bg-zinc-100 text-zinc-600',
    valid:   'bg-green-100 text-green-700',
    invalid: 'bg-red-100 text-red-700',
  }
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium capitalize ${styles[status] ?? styles['pending']}`}>
      {status}
    </span>
  )
}

function formatTs(ts: string) {
  return new Date(ts).toLocaleString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

interface MappingUploadRowProps {
  upload: AdminMappingUpload
  note: AdminNote | null
  onSave: (uploadId: string, note: string) => Promise<{ error: string | null }>
}

function MappingUploadRow({ upload, note, onSave }: MappingUploadRowProps) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <>
      <div className="flex items-start justify-between gap-3 rounded-lg border border-zinc-100 px-3 py-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-medium text-zinc-800" title={upload.original_filename}>
            {upload.original_filename}
          </p>
          <p className="mt-0.5 text-xs text-zinc-400">
            {formatTs(upload.created_at)}
            {upload.row_count != null && (
              <span className="ml-1.5 text-zinc-500">· {upload.row_count} rows</span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <NoteCell
            hasNote={!!note}
            isOpen={isOpen}
            onToggle={() => setIsOpen((v) => !v)}
          />
          <StatusBadge status={upload.validation_status} />
        </div>
      </div>
      {isOpen && (
        <div className="rounded-b-lg border border-t-0 border-zinc-100 bg-amber-50 px-3 py-2">
          <NoteExpandRow
            existingNote={note?.note ?? null}
            onSave={(text) => onSave(upload.id, text)}
            colSpan={1}
            onClose={() => setIsOpen(false)}
          />
        </div>
      )}
    </>
  )
}
```

> **Note:** `NoteExpandRow` renders `<td>` elements designed for a `<table>`. For the mapping history (which uses `<div>` layout), replace the `<td colSpan>` wrapper in `NoteExpandRow` with a fragment — or extract the textarea+buttons into a shared non-table component. The cleanest fix: add an optional `asDiv` prop to `NoteExpandRow` that renders a `<div>` instead of `<tr><td>`.

- [ ] **Step 2: Update NoteExpandRow to support `asDiv` mode**

In `web/components/admin/InlineNoteRow.tsx`, update `NoteExpandRow`:

```typescript
export function NoteExpandRow({
  existingNote,
  onSave,
  colSpan,
  onClose,
  asDiv = false,
}: NoteProps & { onClose: () => void; asDiv?: boolean }) {
  const [text, setText] = useState(existingNote ?? '')
  const [isPending, startTransition] = useTransition()
  const [error, setError] = useState<string | null>(null)

  function handleSave() {
    startTransition(async () => {
      const result = await onSave(text)
      if (result.error) {
        setError(result.error)
      } else {
        onClose()
      }
    })
  }

  const inner = (
    <>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={2}
        placeholder="Note for Claude Code…"
        className="w-full resize-none rounded border border-amber-200 bg-white px-2 py-1.5 text-xs text-zinc-800 placeholder:text-zinc-400 focus:border-amber-400 focus:outline-none"
      />
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
      <div className="mt-1.5 flex gap-2">
        <button
          type="button"
          onClick={handleSave}
          disabled={isPending || !text.trim()}
          className="rounded bg-zinc-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
        >
          {isPending ? 'Saving…' : 'Save note'}
        </button>
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-zinc-200 bg-white px-3 py-1 text-xs text-zinc-600"
        >
          Cancel
        </button>
      </div>
    </>
  )

  if (asDiv) return <div>{inner}</div>

  return (
    <tr className="bg-amber-50">
      <td colSpan={colSpan} className="px-3 py-2">{inner}</td>
    </tr>
  )
}
```

Then in `MappingUploadRow`, use `<NoteExpandRow asDiv ... />` instead of wrapping in a div.

- [ ] **Step 3: Complete the MappingUploadHistory component** (add the list wrapper)

At the bottom of `mapping-upload-history.tsx`, add:

```typescript
interface MappingUploadHistoryProps {
  uploads: AdminMappingUpload[]
  notes: Record<string, AdminNote>
  onSave: (uploadId: string, note: string) => Promise<{ error: string | null }>
}

export function MappingUploadHistory({ uploads, notes, onSave }: MappingUploadHistoryProps) {
  if (uploads.length === 0) {
    return <p className="py-3 text-center text-xs text-zinc-400">No uploads yet.</p>
  }

  return (
    <div className="space-y-1.5">
      {uploads.map((upload) => (
        <MappingUploadRow
          key={upload.id}
          upload={upload}
          note={notes[upload.id] ?? null}
          onSave={onSave}
        />
      ))}
    </div>
  )
}
```

- [ ] **Step 4: Verify TypeScript**

```bash
cd web && npx tsc --noEmit
```

- [ ] **Step 5: Commit**

```bash
git add web/components/mapping-upload-history.tsx web/components/admin/InlineNoteRow.tsx
git commit -m "feat(admin): add inline notes to MappingUploadHistory"
```

---

## Task 15: Wire up admin/page.tsx

**Files:**
- Modify: `web/app/(app)/projects/[projectId]/admin/page.tsx`

- [ ] **Step 1: Check Next.js searchParams API**

Before writing, confirm the `searchParams` prop type for server components in this version:

```bash
grep -r "searchParams" /home/yatbond/projects/financial\ chatbot/web/node_modules/next/dist/docs/ 2>/dev/null | head -20
```

Expected: documentation confirming `searchParams` is `Promise<{ [key: string]: string | string[] | undefined }>`.

- [ ] **Step 2: Rewrite admin/page.tsx**

```typescript
// web/app/(app)/projects/[projectId]/admin/page.tsx
import { getMappingUploads, getMappingStats, getQueryLogs, getDiscrepancies, getAdminNotes, saveAdminNote } from './actions'
import { MappingUploadForm } from '@/components/mapping-upload-form'
import { MappingUploadHistory } from '@/components/mapping-upload-history'
import { AdminTabs, type AdminTab } from '@/components/admin/AdminTabs'
import { QueryLogsTab } from '@/components/admin/QueryLogsTab'
import { DiscrepanciesTab } from '@/components/admin/DiscrepanciesTab'
import { ExportButton } from '@/components/admin/ExportButton'
import type { AdminMappingUpload, MappingType, QueryMode, ResponseType } from '@/lib/types/database'

const VALID_TABS = ['mappings', 'query-logs', 'discrepancies'] as const

interface AdminPageProps {
  params: Promise<{ projectId: string }>
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>
}

export default async function AdminPage({ params, searchParams }: AdminPageProps) {
  const { projectId } = await params
  const sp = await searchParams

  const rawTab = typeof sp.tab === 'string' ? sp.tab : 'mappings'
  const tab: AdminTab = (VALID_TABS as readonly string[]).includes(rawTab)
    ? (rawTab as AdminTab)
    : 'mappings'

  const rawPage = typeof sp.page === 'string' ? parseInt(sp.page, 10) : 1
  const page = isNaN(rawPage) || rawPage < 1 ? 1 : rawPage
  const mode = typeof sp.mode === 'string' ? (sp.mode as QueryMode) : null
  const type = typeof sp.type === 'string' ? (sp.type as ResponseType) : null

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-6">
      <div className="flex items-center justify-between">
        <AdminTabs projectId={projectId} activeTab={tab} />
        <ExportButton projectId={projectId} />
      </div>

      {tab === 'mappings' && (
        <MappingsTab projectId={projectId} />
      )}
      {tab === 'query-logs' && (
        <QueryLogsSection projectId={projectId} page={page} mode={mode} type={type} />
      )}
      {tab === 'discrepancies' && (
        <DiscrepanciesSection projectId={projectId} />
      )}
    </div>
  )
}

async function MappingsTab({ projectId }: { projectId: string }) {
  const [stats, ftmUploads, hmUploads] = await Promise.all([
    getMappingStats(),
    getMappingUploads('financial_type_map'),
    getMappingUploads('heading_map'),
  ])
  const allUploadIds = [...ftmUploads, ...hmUploads].map((u) => u.id)
  const notes = await getAdminNotes(allUploadIds)
  const saveNote = saveAdminNote.bind(null, 'mapping_upload')

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-zinc-200 bg-white p-5">
        <h2 className="mb-3 text-sm font-semibold text-zinc-900">Current Mapping State</h2>
        <div className="grid grid-cols-3 gap-3">
          <StatCard label="Financial Types" value={stats.financialTypeCount} />
          <StatCard label="Heading Entries" value={stats.headingCount} />
          <StatCard label="Heading Aliases" value={stats.aliasCount} />
        </div>
      </div>
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <MappingSection
          title="Financial Type Map"
          description={
            <>
              Maps raw financial type strings from Excel to canonical names.
              Required columns: <code className="rounded bg-zinc-100 px-1 text-xs">Raw_Financial_Type</code>,{' '}
              <code className="rounded bg-zinc-100 px-1 text-xs">Clean_Financial_Type</code>.
              Optional: <code className="rounded bg-zinc-100 px-1 text-xs">Acronyms</code> (pipe-separated).
            </>
          }
          mappingType="financial_type_map"
          projectId={projectId}
          uploads={ftmUploads}
          notes={notes}
          onSaveNote={(id, note) => saveNote(id, projectId, note)}
        />
        <MappingSection
          title="Heading Map"
          description={
            <>
              Maps item codes to canonical data types and categories.
              Required columns: <code className="rounded bg-zinc-100 px-1 text-xs">Item_Code</code>,{' '}
              <code className="rounded bg-zinc-100 px-1 text-xs">Data_Type</code>,{' '}
              <code className="rounded bg-zinc-100 px-1 text-xs">Friendly_Name</code>.
              Rows without <code className="rounded bg-zinc-100 px-1 text-xs">Item_Code</code> are skipped.
            </>
          }
          mappingType="heading_map"
          projectId={projectId}
          uploads={hmUploads}
          notes={notes}
          onSaveNote={(id, note) => saveNote(id, projectId, note)}
        />
      </div>
    </div>
  )
}

async function QueryLogsSection({
  projectId, page, mode, type,
}: {
  projectId: string
  page: number
  mode: QueryMode | null
  type: ResponseType | null
}) {
  const { logs, total } = await getQueryLogs(projectId, { mode: mode ?? undefined, type: type ?? undefined }, page)
  const notes = await getAdminNotes(logs.map((l) => l.id))
  return <QueryLogsTab projectId={projectId} logs={logs} notes={notes} total={total} page={page} mode={mode} type={type} />
}

async function DiscrepanciesSection({ projectId }: { projectId: string }) {
  const discrepancies = await getDiscrepancies(projectId)
  return <DiscrepanciesTab discrepancies={discrepancies} projectId={projectId} />
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-zinc-50 px-4 py-3">
      <p className="text-2xl font-semibold tabular-nums text-zinc-900">{value}</p>
      <p className="mt-0.5 text-xs text-zinc-500">{label}</p>
    </div>
  )
}

interface MappingSectionProps {
  title: string
  description: React.ReactNode
  mappingType: MappingType
  projectId: string
  uploads: AdminMappingUpload[]
  notes: Record<string, import('@/lib/types/database').AdminNote>
  onSaveNote: (uploadId: string, note: string) => Promise<{ error: string | null }>
}

function MappingSection({ title, description, mappingType, projectId, uploads, notes, onSaveNote }: MappingSectionProps) {
  return (
    <div className="space-y-4 rounded-lg border border-zinc-200 bg-white p-5">
      <div>
        <h2 className="text-sm font-semibold text-zinc-900">{title}</h2>
        <p className="mt-1 text-xs leading-relaxed text-zinc-500">{description}</p>
      </div>
      <MappingUploadForm mappingType={mappingType} projectId={projectId} />
      <div>
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-400">Recent Uploads</h3>
        <MappingUploadHistory uploads={uploads} notes={notes} onSave={onSaveNote} />
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Verify TypeScript**

```bash
cd web && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Run the dev server and manually verify each tab**

```bash
cd web && npm run dev
```

Visit `http://localhost:3000/projects/[any-project-id]/admin`:
- Default tab shows Mappings (existing upload forms + history)
- `?tab=query-logs` shows the query log table (empty state if no logs)
- `?tab=discrepancies` shows discrepancies panel (empty state if none)
- `?tab=query-logs&mode=standard` filters correctly
- `Export for Claude` button downloads a `.md` file

- [ ] **Step 5: Commit**

```bash
git add web/app/\(app\)/projects/\[projectId\]/admin/page.tsx
git commit -m "feat(admin): wire up three-tab admin page (Phase 11)"
```

---

## Task 16: Housekeeping

**Files:**
- Modify: `.gitignore` (project root)

- [ ] **Step 1: Add .superpowers to .gitignore**

```bash
grep -q '\.superpowers' "/home/yatbond/projects/financial chatbot/.gitignore" 2>/dev/null || echo '.superpowers/' >> "/home/yatbond/projects/financial chatbot/.gitignore"
```

- [ ] **Step 2: Commit**

```bash
cd "/home/yatbond/projects/financial chatbot" && git add .gitignore && git commit -m "chore: ignore .superpowers brainstorm artifacts"
```

---

## Self-review notes

- `exportIssues` uses a Supabase join query (`!inner`) which requires FK relationships to be registered in the schema. If those aren't present, replace with two separate fetches (see inline note in Task 7, Step 3).
- `MappingUploadHistory` changed its props signature — callers in other pages (reports page etc.) must be updated to pass `notes` and `onSave`. If those pages don't yet show notes, pass `notes={{}}` and a no-op `onSave`.
- `QueryLogsFilterBar` uses `useSearchParams` which requires a `<Suspense>` boundary in the parent. If the build warns about this, wrap `<QueryLogsFilterBar>` in `<Suspense fallback={null}>` inside `QueryLogsTab`.
