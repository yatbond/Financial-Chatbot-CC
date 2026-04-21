import type { AdminMappingUpload } from '@/lib/types/database'

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
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

interface MappingUploadHistoryProps {
  uploads: AdminMappingUpload[]
}

export function MappingUploadHistory({ uploads }: MappingUploadHistoryProps) {
  if (uploads.length === 0) {
    return <p className="py-3 text-center text-xs text-zinc-400">No uploads yet.</p>
  }

  return (
    <div className="space-y-1.5">
      {uploads.map(upload => (
        <div key={upload.id} className="flex items-start justify-between gap-3 rounded-lg border border-zinc-100 px-3 py-2">
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
          <StatusBadge status={upload.validation_status} />
        </div>
      ))}
    </div>
  )
}
