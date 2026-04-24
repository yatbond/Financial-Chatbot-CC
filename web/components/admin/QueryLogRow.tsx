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
  onSave: (logId: string, note: string) => Promise<{ error: string | null }>
}

export function QueryLogRow({ log, note, onSave }: QueryLogRowProps) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <>
      <tr className="border-b border-zinc-100 hover:bg-zinc-50">
        <td className="max-w-[280px] px-3 py-2.5">
          <span className="block truncate text-xs text-zinc-800" title={log.raw_query}>
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
        <td className="px-3 py-2.5 text-xs tabular-nums text-zinc-500">{log.execution_ms ?? '—'}</td>
        <td className="px-3 py-2.5 text-xs text-zinc-400">{formatTs(log.created_at)}</td>
        <td className="px-3 py-2.5">
          <NoteCell hasNote={!!note} isOpen={isOpen} onToggle={() => setIsOpen((v) => !v)} />
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
