import type { ReportUpload, ValidationStatus } from '@/lib/types/database'

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function StatusBadge({ status }: { status: ValidationStatus }) {
  const styles: Record<ValidationStatus, string> = {
    pending:  'bg-zinc-100 text-zinc-600',
    valid:    'bg-green-100 text-green-700',
    partial:  'bg-amber-100 text-amber-700',
    invalid:  'bg-red-100 text-red-700',
  }
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium capitalize ${styles[status]}`}>
      {status}
    </span>
  )
}

function formatPeriod(month: number, year: number) {
  return `${MONTH_NAMES[month - 1]} ${year}`
}

function formatTimestamp(ts: string) {
  return new Date(ts).toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

interface ReportUploadListProps {
  uploads: ReportUpload[]
}

export function ReportUploadList({ uploads }: ReportUploadListProps) {
  if (uploads.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-zinc-400">
        No reports uploaded yet.
      </p>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-100 text-left text-xs font-medium text-zinc-500">
            <th className="pb-2 pr-4">File</th>
            <th className="pb-2 pr-4">Period</th>
            <th className="pb-2 pr-4">Uploaded</th>
            <th className="pb-2 pr-4">Status</th>
            <th className="pb-2">Active</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-50">
          {uploads.map((upload) => (
            <tr key={upload.id} className="text-zinc-700">
              <td className="py-2.5 pr-4">
                <span className="max-w-[220px] truncate font-medium text-zinc-900" title={upload.original_filename}>
                  {upload.original_filename}
                </span>
              </td>
              <td className="py-2.5 pr-4 text-zinc-600">
                {formatPeriod(upload.report_month, upload.report_year)}
              </td>
              <td className="py-2.5 pr-4 text-zinc-500">
                {formatTimestamp(upload.upload_timestamp ?? upload.created_at)}
              </td>
              <td className="py-2.5 pr-4">
                <StatusBadge status={upload.validation_status} />
              </td>
              <td className="py-2.5">
                {upload.is_active ? (
                  <span className="text-xs font-medium text-green-600">Active</span>
                ) : (
                  <span className="text-xs text-zinc-400">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
