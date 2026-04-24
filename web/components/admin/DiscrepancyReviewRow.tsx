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
  return new Intl.NumberFormat('en-AU', {
    style: 'currency',
    currency: 'AUD',
    maximumFractionDigits: 0,
  }).format(v)
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
        <td className="px-3 py-2.5 text-xs text-zinc-600">{formatPeriod(d.report_month, d.report_year)}</td>
        <td className="px-3 py-2.5 text-xs text-zinc-500">{d.data_type ?? d.item_code ?? '—'}</td>
        <td className="px-3 py-2.5 text-xs font-medium tabular-nums text-red-600">{formatValue(d.old_value)}</td>
        <td className="px-3 py-2.5 text-xs font-medium tabular-nums text-green-600">{formatValue(d.new_value)}</td>
        <td className="px-3 py-2.5">
          {action ? (
            <span className="text-xs font-medium text-zinc-400">
              ▼ {action === 'reviewed' ? 'Reviewing…' : 'Dismissing…'}
            </span>
          ) : (
            <span className="flex gap-2">
              <button type="button" onClick={() => open('reviewed')} className="text-xs text-blue-600 hover:text-blue-800">
                Review
              </button>
              <span className="text-zinc-300">·</span>
              <button type="button" onClick={() => open('dismissed')} className="text-xs text-zinc-400 hover:text-zinc-600">
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
              <button type="button" onClick={close} className="rounded border border-zinc-200 bg-white px-3 py-1 text-xs text-zinc-600">
                Cancel
              </button>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}
