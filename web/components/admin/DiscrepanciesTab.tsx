import { DiscrepancyReviewRow } from './DiscrepancyReviewRow'
import { reviewDiscrepancy } from '@/app/(app)/projects/[projectId]/admin/actions'
import type { Discrepancy } from '@/lib/types/database'

interface DiscrepanciesTabProps {
  discrepancies: Discrepancy[]
  projectId: string
}

export function DiscrepanciesTab({ discrepancies, projectId }: DiscrepanciesTabProps) {
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
                  onReview={(id, status, note) => reviewDiscrepancy(id, status, note, projectId)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
