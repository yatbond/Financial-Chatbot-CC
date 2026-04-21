import { getMappingUploads, getMappingStats } from './actions'
import { MappingUploadForm } from '@/components/mapping-upload-form'
import { MappingUploadHistory } from '@/components/mapping-upload-history'
import type { AdminMappingUpload, MappingType } from '@/lib/types/database'

interface AdminPageProps {
  params: Promise<{ projectId: string }>
}

export default async function AdminPage({ params }: AdminPageProps) {
  const { projectId } = await params

  const [stats, ftmUploads, hmUploads] = await Promise.all([
    getMappingStats(),
    getMappingUploads('financial_type_map'),
    getMappingUploads('heading_map'),
  ])

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <div className="rounded-lg border border-zinc-200 bg-white p-5">
        <h2 className="mb-3 text-sm font-semibold text-zinc-900">Current Mapping State</h2>
        <div className="grid grid-cols-3 gap-3">
          <StatCard label="Financial Types" value={stats.financialTypeCount} />
          <StatCard label="Heading Entries" value={stats.headingCount} />
          <StatCard label="Heading Aliases" value={stats.aliasCount} />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <MappingSection
          title="Financial Type Map"
          description={
            <>
              Maps raw financial type strings from Excel to canonical names.
              Required columns: <code className="rounded bg-zinc-100 px-1 text-xs">Raw_Financial_Type</code>,{' '}
              <code className="rounded bg-zinc-100 px-1 text-xs">Clean_Financial_Type</code>.
              Optional: <code className="rounded bg-zinc-100 px-1 text-xs">Acronyms</code> (pipe-separated).
            </>
          }
          mappingType="financial_type_map"
          projectId={projectId}
          uploads={ftmUploads}
        />
        <MappingSection
          title="Heading Map"
          description={
            <>
              Maps item codes to canonical data types and categories.
              Required columns: <code className="rounded bg-zinc-100 px-1 text-xs">Item_Code</code>,{' '}
              <code className="rounded bg-zinc-100 px-1 text-xs">Data_Type</code>,{' '}
              <code className="rounded bg-zinc-100 px-1 text-xs">Friendly_Name</code>.
              Rows without <code className="rounded bg-zinc-100 px-1 text-xs">Item_Code</code> are skipped.
            </>
          }
          mappingType="heading_map"
          projectId={projectId}
          uploads={hmUploads}
        />
      </div>
    </div>
  )
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-zinc-50 px-4 py-3">
      <p className="text-2xl font-semibold tabular-nums text-zinc-900">{value}</p>
      <p className="mt-0.5 text-xs text-zinc-500">{label}</p>
    </div>
  )
}

interface MappingSectionProps {
  title: string
  description: React.ReactNode
  mappingType: MappingType
  projectId: string
  uploads: AdminMappingUpload[]
}

function MappingSection({ title, description, mappingType, projectId, uploads }: MappingSectionProps) {
  return (
    <div className="space-y-4 rounded-lg border border-zinc-200 bg-white p-5">
      <div>
        <h2 className="text-sm font-semibold text-zinc-900">{title}</h2>
        <p className="mt-1 text-xs leading-relaxed text-zinc-500">{description}</p>
      </div>
      <MappingUploadForm mappingType={mappingType} projectId={projectId} />
      <div>
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-400">Recent Uploads</h3>
        <MappingUploadHistory uploads={uploads} />
      </div>
    </div>
  )
}
