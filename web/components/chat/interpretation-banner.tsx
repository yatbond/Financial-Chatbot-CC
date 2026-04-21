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
