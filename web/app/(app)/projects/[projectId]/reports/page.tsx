import { getReportUploads } from './actions'
import { ReportUploadForm } from '@/components/report-upload-form'
import { ReportUploadList } from '@/components/report-upload-list'

interface ReportsPageProps {
  params: Promise<{ projectId: string }>
}

export default async function ReportsPage({ params }: ReportsPageProps) {
  const { projectId } = await params
  const uploads = await getReportUploads(projectId)

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <div className="rounded-lg border border-zinc-200 bg-white p-5">
        <h2 className="mb-1 text-sm font-semibold text-zinc-900">Upload Report</h2>
        <p className="mb-4 text-xs text-zinc-500">
          Upload an Excel financial report for this project. Select the reporting period and attach the file.
          The report will be queued for ingestion once uploaded.
        </p>
        <ReportUploadForm projectId={projectId} />
      </div>

      <div className="rounded-lg border border-zinc-200 bg-white p-5">
        <h2 className="mb-4 text-sm font-semibold text-zinc-900">
          Upload History
          {uploads.length > 0 && (
            <span className="ml-2 rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-normal text-zinc-500">
              {uploads.length}
            </span>
          )}
        </h2>
        <ReportUploadList uploads={uploads} />
      </div>
    </div>
  )
}
