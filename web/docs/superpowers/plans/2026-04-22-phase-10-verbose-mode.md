# Phase 10: Verbose Mode, Query Logging & Discrepancy Visibility — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the existing ModeContext toggle into the API, add verbose trace fields to the interpretation banner and a collapsible panel to the result table, and log every resolved query to `query_logs`.

**Architecture:** `mode` is added to `ChatRequest` so the client sends it; the resolver attaches mock `verbose_trace` + `discrepancy_warnings` in verbose mode; the API route inserts a `query_logs` row after each resolution; UI components receive `mode` via prop-drilling from `ChatShell`.

**Tech Stack:** Next.js 15 App Router, TypeScript, Tailwind v4, `@clerk/nextjs` (server-side `auth()`), `@supabase/supabase-js` (service-role INSERT)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `lib/chat/types.ts` | Modify | Add `VerboseTrace`, `DiscrepancyWarning` types; extend `ChatRequest` + `ResultResponse` |
| `lib/chat/resolver.ts` | Modify | Attach mock verbose trace and discrepancy warnings when `mode === 'verbose'` |
| `app/api/projects/[projectId]/chat/route.ts` | Modify | Forward `mode`, measure `execution_ms`, fire-and-forget `query_logs` INSERT |
| `components/chat/chat-shell.tsx` | Modify | Read `useMode()`, include `mode` in every POST body; pass `mode` to `ChatMessageItem` |
| `components/chat/chat-message-item.tsx` | Modify | Accept `mode` prop, forward to `InterpretationBanner` and `ResultTable` |
| `components/chat/interpretation-banner.tsx` | Modify | Show verbose trace fields (row, cell, timestamp, workbook) when `mode === 'verbose'` |
| `components/chat/result-table.tsx` | Modify | Add collapsible verbose panel below table; show discrepancy warnings in verbose mode |

---

### Task 1: Extend chat types

**Files:**
- Modify: `lib/chat/types.ts`

- [ ] **Step 1: Add VerboseTrace, DiscrepancyWarning, extend ChatRequest and ResultResponse**

Replace the content of `lib/chat/types.ts` with the following (full file, all existing content preserved and extended):

```typescript
// Chat system types for Phase 10.
export type QueryMode = 'standard' | 'verbose'

// ─── Session context ────────────────────────────────────────────────────────
export interface SessionContext {
  project_code?: string
  project_name?: string
  period?: string
  sheet_name?: string
  financial_type?: string
  data_type?: string
  last_shortcut?: string
}

// ─── Resolved interpretation ─────────────────────────────────────────────────
export interface ResolvedParams {
  project?: string
  sheet_name?: string
  financial_type?: string
  data_type?: string
  period?: string
  shortcut?: string
  months?: number
}

// ─── Ambiguity option ────────────────────────────────────────────────────────
export interface AmbiguityOption {
  label: string
  params: Partial<ResolvedParams>
}

// ─── Result table ────────────────────────────────────────────────────────────
export type ResultRow = Record<string, string | number | null>

// ─── Verbose trace (per-query source traceability) ───────────────────────────
export interface VerboseTrace {
  row_number: number | null
  cell_reference: string | null
  upload_timestamp: string | null
  source_workbook: string | null
}

// ─── Discrepancy warning (superseded value on a result row) ──────────────────
export interface DiscrepancyWarning {
  item: string
  old_value: number
  new_value: number
  superseded_by_upload_id: string
}

// ─── API responses ───────────────────────────────────────────────────────────
export interface ResultResponse {
  type: 'result'
  interpretation: ResolvedParams
  columns: string[]
  rows: ResultRow[]
  summary?: string
  warning?: string
  context_update?: Partial<SessionContext>
  verbose_trace?: VerboseTrace
  discrepancy_warnings?: DiscrepancyWarning[]
}

export interface AmbiguityResponse {
  type: 'ambiguity'
  interpretation: Partial<ResolvedParams>
  prompt: string
  options: AmbiguityOption[]
  context_update?: Partial<SessionContext>
}

export interface MissingResponse {
  type: 'missing'
  interpretation: Partial<ResolvedParams>
  message: string
}

export interface InfoResponse {
  type: 'info'
  title: string
  content: string
}

export interface ErrorResponse {
  type: 'error'
  message: string
}

export type ChatResponse =
  | ResultResponse
  | AmbiguityResponse
  | MissingResponse
  | InfoResponse
  | ErrorResponse

// ─── Chat message (local UI state) ──────────────────────────────────────────
export interface UserMessage {
  id: string
  role: 'user'
  text: string
}

export interface AssistantMessage {
  id: string
  role: 'assistant'
  query: string
  response: ChatResponse
  selected_option?: number
}

export type ChatMessage = UserMessage | AssistantMessage

// ─── API request body ────────────────────────────────────────────────────────
export interface ChatRequest {
  query: string
  context: SessionContext
  mode?: QueryMode
  selected_option_index?: number
  prior_options?: AmbiguityOption[]
}
```

- [ ] **Step 2: Verify TypeScript sees no errors**

```bash
cd "/home/yatbond/projects/financial chatbot/web" && npx tsc --noEmit 2>&1 | head -30
```

Expected: zero errors from `lib/chat/types.ts`. Errors from other files about new missing fields are expected at this stage.

- [ ] **Step 3: Commit**

```bash
cd "/home/yatbond/projects/financial chatbot/web"
git add lib/chat/types.ts
git commit -m "feat(phase-10): extend chat types with VerboseTrace, DiscrepancyWarning, mode field"
```

---

### Task 2: Add mock verbose trace to resolver

**Files:**
- Modify: `lib/chat/resolver.ts`

The resolver must (a) read `req.mode` (defaulting to 'standard') and (b) when mode is 'verbose', attach `verbose_trace` and `discrepancy_warnings` to every `ResultResponse` it returns.

- [ ] **Step 1: Add a mock trace helper and a mock discrepancy helper after the existing mock data generators section (after line ~258 in resolver.ts)**

Add these two functions after `mockCashFlowRows()`:

```typescript
function mockVerboseTrace(): VerboseTrace {
  return {
    row_number: 42,
    cell_reference: 'C15',
    upload_timestamp: '2026-02-05T09:30:00.000Z',
    source_workbook: 'Feb-2026-Financial-Report.xlsx',
  }
}

function mockDiscrepancyWarnings(): DiscrepancyWarning[] {
  return [
    {
      item: 'VO/CE',
      old_value: 500_000,
      new_value: 620_000,
      superseded_by_upload_id: 'mock-upload-789',
    },
  ]
}
```

- [ ] **Step 2: Update the import at the top of resolver.ts to include the new types**

The existing import is:
```typescript
import {
  type ChatRequest,
  type ChatResponse,
  type ResolvedParams,
  type AmbiguityOption,
  type ResultRow,
  type SessionContext,
} from './types'
```

Replace with:
```typescript
import {
  type ChatRequest,
  type ChatResponse,
  type ResolvedParams,
  type AmbiguityOption,
  type ResultRow,
  type SessionContext,
  type VerboseTrace,
  type DiscrepancyWarning,
} from './types'
```

- [ ] **Step 3: Add a helper that decorates any ResultResponse with verbose fields**

Add this function after `mockDiscrepancyWarnings()`:

```typescript
function withVerbose(
  res: Extract<ChatResponse, { type: 'result' }>,
  mode: string,
  withDiscrepancies = false,
): Extract<ChatResponse, { type: 'result' }> {
  if (mode !== 'verbose') return res
  return {
    ...res,
    verbose_trace: mockVerboseTrace(),
    ...(withDiscrepancies ? { discrepancy_warnings: mockDiscrepancyWarnings() } : {}),
  }
}
```

- [ ] **Step 4: Wrap every ResultResponse return in `handleShortcut` and `resolveQuery` with `withVerbose`**

In `handleShortcut`, add `mode` as a parameter and wrap each `return { type: 'result', ... }` call:

Change the signature from:
```typescript
function handleShortcut(shortcut: string, q: string, ctx: SessionContext): ChatResponse {
```
to:
```typescript
function handleShortcut(shortcut: string, q: string, ctx: SessionContext, mode: string): ChatResponse {
```

Then for each `return { type: 'result', ... }` block in `handleShortcut`, wrap it with `withVerbose(...)`. Add `withDiscrepancies = true` only for the `risk` shortcut case. The full list of changes inside `handleShortcut`:

- `case 'list'`: change `return { type: 'result', ... }` to `return withVerbose({ type: 'result', ... }, mode)`
- `case 'risk'`: change `return { type: 'result', ... }` to `return withVerbose({ type: 'result', ... }, mode, true)` ← discrepancies enabled here
- `case 'cash flow'`: `return withVerbose({ type: 'result', ... }, mode)`
- `case 'analyze'/'analyse'`: `return withVerbose({ type: 'result', ... }, mode)`
- `case 'trend'` (resolved branch): `return withVerbose({ type: 'result', ... }, mode)`
- `case 'compare'` (resolved branch): `return withVerbose({ type: 'result', ... }, mode)`
- `case 'total'` (resolved branch): `return withVerbose({ type: 'result', ... }, mode)`
- `case 'detail'`: `return withVerbose({ type: 'result', ... }, mode)`

Then update `handleShortcut` call site in `resolveQuery`:

Change:
```typescript
  if (shortcut) {
    return handleShortcut(shortcut, q, ctx)
  }
```
to:
```typescript
  const mode = req.mode ?? 'standard'
  if (shortcut) {
    return handleShortcut(shortcut, q, ctx, mode)
  }
```

And wrap the two `return { type: 'result', ... }` statements at the bottom of `resolveQuery` (the ambiguity-selection branch and the fully-resolved branch) with `withVerbose(..., mode)`:

Ambiguity-selection branch (around line 498):
```typescript
    const { columns, rows } = mockValueRows(ft ?? 'Projection', dt, period)
    return withVerbose({
      type: 'result',
      interpretation: { financial_type: ft ?? undefined, data_type: dt, sheet_name: sheet, period },
      columns,
      rows,
      context_update: { financial_type: ft ?? undefined, data_type: dt, sheet_name: sheet },
    }, mode)
```

Fully-resolved branch (around line 618):
```typescript
  const { columns, rows } = mockValueRows(ft!, dt!, period)
  return withVerbose({
    type: 'result',
    interpretation: {
      financial_type: ft!,
      data_type: dt!,
      sheet_name: resolvedSheet,
      period,
    },
    columns,
    rows,
    context_update: {
      financial_type: ft!,
      data_type: dt!,
      sheet_name: resolvedSheet,
    },
  }, mode)
```

Also declare `mode` before the shortcut check in `resolveQuery` and move the existing `const mode = req.mode ?? 'standard'` line to the TOP of `resolveQuery` (before the ambiguity-selection `if` block), so it's available in both branches:

```typescript
export function resolveQuery(req: ChatRequest): ChatResponse {
  const mode = req.mode ?? 'standard'

  // Handle ambiguity selection from prior turn
  if (req.selected_option_index !== undefined && req.prior_options) {
    // ... existing code ...
    return withVerbose({ type: 'result', ... }, mode)
  }
  // ... rest of function ...
}
```

- [ ] **Step 5: Verify TypeScript**

```bash
cd "/home/yatbond/projects/financial chatbot/web" && npx tsc --noEmit 2>&1 | head -30
```

Expected: no errors in `lib/chat/resolver.ts`.

- [ ] **Step 6: Commit**

```bash
cd "/home/yatbond/projects/financial chatbot/web"
git add lib/chat/resolver.ts
git commit -m "feat(phase-10): attach mock verbose trace and discrepancy warnings in verbose mode"
```

---

### Task 3: Update chat API route — forward mode + insert query_log

**Files:**
- Modify: `app/api/projects/[projectId]/chat/route.ts`

- [ ] **Step 1: Replace route.ts with the updated version**

```typescript
import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'
import { resolveQuery } from '@/lib/chat/resolver'
import { createServerSupabase } from '@/lib/supabase/server'
import type { ChatRequest, ChatResponse } from '@/lib/chat/types'
import type { QueryLogInsert, ResponseType } from '@/lib/types/database'

function toResponseType(res: ChatResponse): ResponseType | null {
  if (res.type === 'ambiguity') return 'ambiguity'
  if (res.type === 'missing') return 'missing'
  if (res.type === 'error') return 'error'
  if (res.type === 'info') return null
  if (res.type === 'result') {
    const shortcut = res.interpretation.shortcut
    if (shortcut === 'trend') return 'trend'
    if (shortcut === 'compare') return 'compare'
    if (shortcut === 'total') return 'total'
    if (shortcut === 'detail') return 'detail'
    if (shortcut === 'risk') return 'risk'
    if (shortcut === 'cash flow') return 'cash_flow'
    if (shortcut === 'list') return 'list'
    if (shortcut === 'analyze' || shortcut === 'analyse') return 'table'
    return res.rows.length > 1 ? 'table' : 'value'
  }
  return null
}

async function insertQueryLog(
  projectId: string,
  body: ChatRequest,
  response: ChatResponse,
  executionMs: number,
  userId: string,
): Promise<void> {
  const supabase = createServerSupabase()
  const interp = response.type === 'result' || response.type === 'ambiguity' || response.type === 'missing'
    ? response.interpretation
    : {}

  const log: QueryLogInsert = {
    project_id: projectId,
    user_id: userId,
    raw_query: body.query,
    resolved_sheet_name: (interp as { sheet_name?: string }).sheet_name ?? null,
    resolved_financial_type: (interp as { financial_type?: string }).financial_type ?? null,
    resolved_data_type: (interp as { data_type?: string }).data_type ?? null,
    resolved_item_code: null,
    resolved_month: null,
    resolved_year: null,
    resolved_shortcut: (interp as { shortcut?: string }).shortcut ?? null,
    interpretation_options: response.type === 'ambiguity'
      ? response.options.map(o => ({ label: o.label, params: o.params as Record<string, string | number | undefined> }))
      : null,
    selected_option_index: body.selected_option_index ?? null,
    was_ambiguous: response.type === 'ambiguity',
    mode: body.mode ?? 'standard',
    response_type: toResponseType(response),
    execution_ms: executionMs,
  }

  await supabase.from('query_logs').insert(log)
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ projectId: string }> }
) {
  const { projectId } = await params

  let body: ChatRequest
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ type: 'error', message: 'Invalid request body.' }, { status: 400 })
  }

  if (!body.query?.trim()) {
    return NextResponse.json({ type: 'error', message: 'Query is required.' }, { status: 400 })
  }

  if (!body.context) body.context = {}
  if (!body.context.project_code) body.context.project_code = projectId

  const startMs = Date.now()

  let response: ChatResponse
  try {
    response = resolveQuery(body)
  } catch (err) {
    console.error('[chat/route] resolver error', err)
    return NextResponse.json({ type: 'error', message: 'Query resolution failed.' }, { status: 500 })
  }

  const executionMs = Date.now() - startMs

  // Fire-and-forget — never let logging break the response
  try {
    const { userId } = await auth()
    await insertQueryLog(projectId, body, response, executionMs, userId ?? 'anon')
  } catch (err) {
    console.warn('[chat/route] query_log insert failed (non-fatal)', err)
  }

  return NextResponse.json(response)
}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd "/home/yatbond/projects/financial chatbot/web" && npx tsc --noEmit 2>&1 | head -30
```

Expected: no errors in the route file.

- [ ] **Step 3: Commit**

```bash
cd "/home/yatbond/projects/financial chatbot/web"
git add "app/api/projects/[projectId]/chat/route.ts"
git commit -m "feat(phase-10): add query_logs INSERT and mode forwarding to chat API route"
```

---

### Task 4: Wire mode into ChatShell requests

**Files:**
- Modify: `components/chat/chat-shell.tsx`

- [ ] **Step 1: Add useMode import and pass mode in requests + to ChatMessageItem**

In `chat-shell.tsx`, make the following changes:

1. Add import at top:
```typescript
import { useMode } from '@/lib/mode-context'
```

2. Inside `ChatShell`, after the existing state declarations, add:
```typescript
  const { mode } = useMode()
```

3. In `handleSubmit`, add `mode` to the request body:
```typescript
    const body: ChatRequest = { query, context, mode }
```

4. In `handleOptionSelect`, add `mode` to the request body:
```typescript
    const body: ChatRequest = {
      query: originalQuery,
      context: mergedContext,
      mode,
      selected_option_index: optionIndex,
      prior_options: priorOptions,
    }
```

5. In the render, pass `mode` to each `ChatMessageItem`:
```typescript
        {messages.map((msg) => (
          <ChatMessageItem
            key={msg.id}
            message={msg}
            mode={mode}
            isLastAssistant={msg.id === lastAssistantId}
            onSelectOption={handleOptionSelect}
            isLoading={loading}
          />
        ))}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd "/home/yatbond/projects/financial chatbot/web" && npx tsc --noEmit 2>&1 | head -30
```

Expected: error about `mode` not existing on `ChatMessageItemProps` (will be fixed in Task 7). No errors in `chat-shell.tsx` itself beyond that.

- [ ] **Step 3: Commit**

```bash
cd "/home/yatbond/projects/financial chatbot/web"
git add components/chat/chat-shell.tsx
git commit -m "feat(phase-10): forward mode from ModeContext into chat API requests"
```

---

### Task 5: Update InterpretationBanner with verbose trace fields

**Files:**
- Modify: `components/chat/interpretation-banner.tsx`

- [ ] **Step 1: Replace interpretation-banner.tsx**

```typescript
import type { ResolvedParams, QueryMode, VerboseTrace } from '@/lib/chat/types'

interface InterpretationBannerProps {
  interpretation: Partial<ResolvedParams>
  mode?: QueryMode
  verboseTrace?: VerboseTrace
}

const LABELS: Record<string, string> = {
  project: 'Project',
  sheet_name: 'Sheet',
  financial_type: 'Financial Type',
  data_type: 'Data Type',
  period: 'Period',
  shortcut: 'Shortcut',
  months: 'Months',
}

function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString('en-HK', {
      day: 'numeric', month: 'short', year: 'numeric',
    })
  } catch {
    return iso
  }
}

export function InterpretationBanner({ interpretation, mode, verboseTrace }: InterpretationBannerProps) {
  const entries = Object.entries(interpretation).filter(([, v]) => v !== undefined && v !== null)
  const showVerbose = mode === 'verbose' && verboseTrace

  if (entries.length === 0 && !showVerbose) return null

  return (
    <div className="mb-2 rounded-md bg-zinc-50 px-3 py-2 text-xs border border-zinc-200">
      {entries.length > 0 && (
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          <span className="font-medium text-zinc-500 shrink-0">Resolved as:</span>
          {entries.map(([key, value]) => (
            <span key={key} className="text-zinc-700">
              <span className="text-zinc-400">{LABELS[key] ?? key}:</span>{' '}
              <span className="font-medium">{String(value)}</span>
            </span>
          ))}
        </div>
      )}
      {showVerbose && verboseTrace && (
        <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 border-t border-zinc-200 pt-1.5">
          <span className="font-medium text-violet-500 shrink-0">Source:</span>
          {verboseTrace.row_number !== null && (
            <span className="text-zinc-600">
              <span className="text-zinc-400">Row:</span>{' '}
              <span className="font-mono">{verboseTrace.row_number}</span>
            </span>
          )}
          {verboseTrace.cell_reference !== null && (
            <span className="text-zinc-600">
              <span className="text-zinc-400">Cell:</span>{' '}
              <span className="font-mono">{verboseTrace.cell_reference}</span>
            </span>
          )}
          {verboseTrace.upload_timestamp !== null && (
            <span className="text-zinc-600">
              <span className="text-zinc-400">Uploaded:</span>{' '}
              <span className="font-medium">{formatTimestamp(verboseTrace.upload_timestamp)}</span>
            </span>
          )}
          {verboseTrace.source_workbook !== null && (
            <span className="text-zinc-600">
              <span className="text-zinc-400">Workbook:</span>{' '}
              <span className="font-medium">{verboseTrace.source_workbook}</span>
            </span>
          )}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd "/home/yatbond/projects/financial chatbot/web" && npx tsc --noEmit 2>&1 | head -30
```

- [ ] **Step 3: Commit**

```bash
cd "/home/yatbond/projects/financial chatbot/web"
git add components/chat/interpretation-banner.tsx
git commit -m "feat(phase-10): add verbose source trace fields to interpretation banner"
```

---

### Task 6: Add collapsible verbose panel to ResultTable

**Files:**
- Modify: `components/chat/result-table.tsx`

- [ ] **Step 1: Replace result-table.tsx**

```typescript
'use client'

import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  type ColumnDef,
} from '@tanstack/react-table'
import { useMemo, useState } from 'react'
import { cn } from '@/lib/utils'
import type { ResultRow, QueryMode, DiscrepancyWarning } from '@/lib/chat/types'

interface ResultTableProps {
  columns: string[]
  rows: ResultRow[]
  className?: string
  mode?: QueryMode
  discrepancyWarnings?: DiscrepancyWarning[]
}

function formatCell(value: string | number | null): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') {
    if (Math.abs(value) >= 1000) {
      return value.toLocaleString('en-HK', { maximumFractionDigits: 0 })
    }
    return String(value)
  }
  return String(value)
}

function isNumericColumn(rows: ResultRow[], col: string): boolean {
  return rows.some(r => typeof r[col] === 'number')
}

function formatCurrency(n: number): string {
  return n.toLocaleString('en-HK', { maximumFractionDigits: 0 })
}

export function ResultTable({ columns, rows, className, mode, discrepancyWarnings }: ResultTableProps) {
  const [verboseOpen, setVerboseOpen] = useState(false)

  const colDefs = useMemo<ColumnDef<ResultRow>[]>(
    () =>
      columns.map((col) => ({
        id: col,
        accessorKey: col,
        header: col,
        cell: ({ getValue }) => {
          const v = getValue() as string | number | null
          return (
            <span className={typeof v === 'number' && v < 0 ? 'text-red-600' : ''}>
              {formatCell(v)}
            </span>
          )
        },
      })),
    [columns]
  )

  const table = useReactTable({
    data: rows,
    columns: colDefs,
    getCoreRowModel: getCoreRowModel(),
  })

  if (rows.length === 0) {
    return <p className="mt-2 text-xs text-zinc-400">No data found.</p>
  }

  const showVerbosePanel = mode === 'verbose'

  return (
    <div className={cn('mt-3', className)}>
      <div className="overflow-x-auto rounded-md border border-zinc-200">
        <table className="w-full text-xs">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="border-b border-zinc-200 bg-zinc-50">
                {hg.headers.map((header) => {
                  const numeric = isNumericColumn(rows, header.id)
                  return (
                    <th
                      key={header.id}
                      className={cn(
                        'px-3 py-2 font-medium text-zinc-500 whitespace-nowrap',
                        numeric ? 'text-right' : 'text-left'
                      )}
                    >
                      {flexRender(header.column.columnDef.header, header.getContext())}
                    </th>
                  )
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row, i) => (
              <tr
                key={row.id}
                className={cn(
                  'border-b border-zinc-100 last:border-0',
                  i % 2 === 0 ? 'bg-white' : 'bg-zinc-50/50'
                )}
              >
                {row.getVisibleCells().map((cell) => {
                  const numeric = isNumericColumn(rows, cell.column.id)
                  return (
                    <td
                      key={cell.id}
                      className={cn(
                        'px-3 py-2 text-zinc-800 whitespace-nowrap',
                        numeric ? 'text-right tabular-nums' : 'text-left'
                      )}
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showVerbosePanel && (
        <div className="mt-1 rounded-md border border-violet-100 bg-violet-50/50 text-xs">
          <button
            onClick={() => setVerboseOpen((o) => !o)}
            className="flex w-full items-center gap-1.5 px-3 py-1.5 text-left text-violet-600 hover:text-violet-800"
          >
            <svg
              className={cn('h-3 w-3 transition-transform', verboseOpen ? 'rotate-90' : '')}
              fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
            </svg>
            <span className="font-medium">Verbose details</span>
            {discrepancyWarnings && discrepancyWarnings.length > 0 && (
              <span className="ml-1 rounded-full bg-amber-100 px-1.5 py-0.5 text-amber-700 font-semibold">
                {discrepancyWarnings.length} discrepanc{discrepancyWarnings.length === 1 ? 'y' : 'ies'}
              </span>
            )}
          </button>

          {verboseOpen && (
            <div className="border-t border-violet-100 px-3 py-2 space-y-1.5">
              {!discrepancyWarnings || discrepancyWarnings.length === 0 ? (
                <p className="text-zinc-500">No discrepancies detected for this result.</p>
              ) : (
                discrepancyWarnings.map((w, i) => (
                  <div
                    key={i}
                    className="flex flex-wrap items-baseline gap-x-2 rounded-md bg-amber-50 border border-amber-200 px-2.5 py-1.5 text-amber-800"
                  >
                    <span className="font-medium">⚠ {w.item}</span>
                    <span className="text-amber-600">
                      previous: <span className="tabular-nums font-medium">HK${formatCurrency(w.old_value)}</span>
                      {' → '}
                      current: <span className="tabular-nums font-medium">HK${formatCurrency(w.new_value)}</span>
                    </span>
                    <span className="text-amber-500 text-[10px]">upload {w.superseded_by_upload_id}</span>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd "/home/yatbond/projects/financial chatbot/web" && npx tsc --noEmit 2>&1 | head -30
```

- [ ] **Step 3: Commit**

```bash
cd "/home/yatbond/projects/financial chatbot/web"
git add components/chat/result-table.tsx
git commit -m "feat(phase-10): add collapsible verbose panel with discrepancy warnings to ResultTable"
```

---

### Task 7: Update ChatMessageItem to pass mode through

**Files:**
- Modify: `components/chat/chat-message-item.tsx`

- [ ] **Step 1: Replace chat-message-item.tsx**

```typescript
'use client'

import type { ChatMessage, AmbiguityOption, QueryMode } from '@/lib/chat/types'
import { InterpretationBanner } from './interpretation-banner'
import { AmbiguityOptions } from './ambiguity-options'
import { ResultTable } from './result-table'

interface ChatMessageItemProps {
  message: ChatMessage
  mode: QueryMode
  isLastAssistant: boolean
  onSelectOption: (messageId: string, index: number, option: AmbiguityOption) => void
  isLoading?: boolean
}

export function ChatMessageItem({
  message,
  mode,
  isLastAssistant,
  onSelectOption,
  isLoading,
}: ChatMessageItemProps) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[70%] rounded-2xl rounded-tr-sm bg-zinc-900 px-4 py-2.5 text-sm text-white">
          {message.text}
        </div>
      </div>
    )
  }

  const { response, selected_option } = message

  return (
    <div className="flex flex-col gap-1">
      <div className="max-w-[85%] rounded-2xl rounded-tl-sm bg-white border border-zinc-200 px-4 py-3 text-sm text-zinc-800 shadow-xs">

        {response.type === 'result' && (
          <>
            <InterpretationBanner
              interpretation={response.interpretation}
              mode={mode}
              verboseTrace={response.verbose_trace}
            />
            {response.summary && (
              <p className="mb-1 text-xs text-zinc-500">{response.summary}</p>
            )}
            {response.warning && (
              <p className="mb-2 rounded-md bg-amber-50 px-3 py-1.5 text-xs text-amber-700 border border-amber-200">
                ⚠ {response.warning}
              </p>
            )}
            <ResultTable
              columns={response.columns}
              rows={response.rows}
              mode={mode}
              discrepancyWarnings={response.discrepancy_warnings}
            />
          </>
        )}

        {response.type === 'ambiguity' && (
          <>
            {Object.keys(response.interpretation).length > 0 && (
              <InterpretationBanner interpretation={response.interpretation} mode={mode} />
            )}
            <AmbiguityOptions
              prompt={response.prompt}
              options={response.options}
              onSelect={(index, option) => onSelectOption(message.id, index, option)}
              disabled={isLoading}
              selectedIndex={selected_option}
            />
          </>
        )}

        {response.type === 'missing' && (
          <>
            <InterpretationBanner interpretation={response.interpretation} mode={mode} />
            <p className="text-sm text-zinc-500">{response.message}</p>
          </>
        )}

        {response.type === 'info' && (
          <div>
            <p className="mb-2 font-medium text-zinc-800">{response.title}</p>
            <pre className="whitespace-pre-wrap font-mono text-xs text-zinc-600 leading-relaxed">
              {response.content}
            </pre>
          </div>
        )}

        {response.type === 'error' && (
          <p className="text-sm text-red-600">{response.message}</p>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Full TypeScript check**

```bash
cd "/home/yatbond/projects/financial chatbot/web" && npx tsc --noEmit 2>&1 | head -50
```

Expected: **zero errors** across all files.

- [ ] **Step 3: Commit**

```bash
cd "/home/yatbond/projects/financial chatbot/web"
git add components/chat/chat-message-item.tsx
git commit -m "feat(phase-10): wire mode prop through ChatMessageItem to banner and table"
```

---

### Task 8: Final build check + manual test

- [ ] **Step 1: Production build**

```bash
cd "/home/yatbond/projects/financial chatbot/web" && npm run build 2>&1 | tail -30
```

Expected: build completes without errors.

- [ ] **Step 2: Start dev server**

```bash
cd "/home/yatbond/projects/financial chatbot/web" && npm run dev
```

- [ ] **Step 3: Manual test — Standard mode**

1. Open the chat page for any project
2. Ensure "Standard" is selected in the mode toggle (top-right)
3. Send query: `projected gp`
4. Verify: interpretation banner shows "Financial Type: Projection | Data Type: Gross Profit" — NO row/cell/workbook fields visible
5. Verify: NO "Verbose details" toggle below the table

- [ ] **Step 4: Manual test — Verbose mode, single result**

1. Click "Verbose" in the mode toggle
2. Send query: `projected gp`
3. Verify: interpretation banner shows resolved params AND a "Source" section with Row: 42 · Cell: C15 · Uploaded: 5 Feb 2026 · Workbook: Feb-2026-Financial-Report.xlsx
4. Verify: A "Verbose details" toggle appears below the table
5. Click it — verify it expands with "No discrepancies detected for this result."

- [ ] **Step 5: Manual test — Verbose mode with discrepancy warning**

1. Still in Verbose mode, send: `risk`
2. Verify: interpretation banner shows verbose source trace
3. Verify: "Verbose details" toggle shows "1 discrepancy" badge
4. Click it — verify amber warning row: "⚠ VO/CE previous: HK$500,000 → current: HK$620,000"

- [ ] **Step 6: Verify query_logs (if Supabase is configured)**

If `NEXT_PUBLIC_SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are set, open the Supabase dashboard → Table Editor → `query_logs`. Confirm a row was inserted for each query with the correct `mode`, `raw_query`, and `execution_ms`.

If env vars are not set, confirm the server logs show `[chat/route] query_log insert failed (non-fatal)` and the chat response still returns correctly.

- [ ] **Step 7: Final commit**

```bash
cd "/home/yatbond/projects/financial chatbot/web"
git add docs/superpowers/plans/2026-04-22-phase-10-verbose-mode.md
git commit -m "docs: add phase-10 implementation plan"
```
