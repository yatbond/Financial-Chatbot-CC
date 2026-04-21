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
