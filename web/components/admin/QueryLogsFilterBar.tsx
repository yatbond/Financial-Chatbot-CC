'use client'

import { useRouter, usePathname, useSearchParams } from 'next/navigation'
import type { QueryMode, ResponseType } from '@/lib/types/database'

const RESPONSE_TYPES: ResponseType[] = [
  'value', 'table', 'trend', 'compare', 'total', 'detail',
  'risk', 'cash_flow', 'list', 'ambiguity', 'missing', 'error',
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
