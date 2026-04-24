import { Suspense } from 'react'
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

export function QueryLogsTab({ projectId, logs, notes, total, page, mode, type }: QueryLogsTabProps) {
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
      <Suspense fallback={null}>
        <QueryLogsFilterBar mode={mode} type={type} from={meta.from} to={meta.to} total={total} />
      </Suspense>

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
