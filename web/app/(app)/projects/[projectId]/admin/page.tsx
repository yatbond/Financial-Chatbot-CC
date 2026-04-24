import React from 'react'
import {
  getMappingUploads,
  getMappingStats,
  getQueryLogs,
  getDiscrepancies,
  getAdminNotes,
  saveAdminNote,
} from './actions'
import { MappingUploadForm } from '@/components/mapping-upload-form'
import { MappingUploadHistory } from '@/components/mapping-upload-history'
import { AdminTabs } from '@/components/admin/AdminTabs'
import { ExportButton } from '@/components/admin/ExportButton'
import { QueryLogsTab } from '@/components/admin/QueryLogsTab'
import { DiscrepanciesTab } from '@/components/admin/DiscrepanciesTab'
import type { AdminTab } from '@/components/admin/AdminTabs'
import type { AdminMappingUpload, MappingType, QueryMode, ResponseType } from '@/lib/types/database'

interface AdminPageProps {
  params: Promise<{ projectId: string }>
  searchParams: Promise<Record<string, string | string[] | undefined>>
}

function parseTab(raw: string | string[] | undefined): AdminTab {
  const v = Array.isArray(raw) ? raw[0] : raw
  if (v === 'query-logs' || v === 'discrepancies') return v
  return 'mappings'
}

function parseNum(raw: string | string[] | undefined, fallback: number): number {
  const v = Array.isArray(raw) ? raw[0] : raw
  const n = parseInt(v ?? '', 10)
  return isNaN(n) || n < 1 ? fallback : n
}

function parseEnum<T extends string>(
  raw: string | string[] | undefined,
  allowed: T[]
): T | null {
  const v = Array.isArray(raw) ? raw[0] : raw
  return v && (allowed as string[]).includes(v) ? (v as T) : null
}

export default async function AdminPage({ params, searchParams }: AdminPageProps) {
  const { projectId } = await params
  const sp = await searchParams

  const tab = parseTab(sp.tab)
  const page = parseNum(sp.page, 1)
  const mode = parseEnum<QueryMode>(sp.mode, ['standard', 'verbose'])
  const type = parseEnum<ResponseType>(sp.type, [
    'value', 'table', 'trend', 'compare', 'total', 'ambiguity', 'missing', 'error',
  ])

  return (
    <div className="min-h-screen bg-zinc-50">
      {/* Header */}
      <div className="border-b border-zinc-200 bg-white">
        <div className="mx-auto max-w-5xl px-6 py-4">
          <div className="flex items-center justify-between">
            <h1 className="text-base font-semibold text-zinc-900">Admin</h1>
            <ExportButton projectId={projectId} />
          </div>
        </div>
        <div className="mx-auto max-w-5xl">
          <AdminTabs projectId={projectId} activeTab={tab} />
        </div>
      </div>

      {/* Content */}
      <div className="mx-auto max-w-5xl px-6 py-6">
        {tab === 'mappings' && (
          <MappingsTab projectId={projectId} />
        )}
        {tab === 'query-logs' && (
          <QueryLogsSection projectId={projectId} page={page} mode={mode} type={type} />
        )}
        {tab === 'discrepancies' && (
          <DiscrepanciesSection projectId={projectId} />
        )}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────
// Mappings tab
// ─────────────────────────────────────────────────────────────

async function MappingsTab({ projectId }: { projectId: string }) {
  const [stats, ftmUploads, hmUploads] = await Promise.all([
    getMappingStats(),
    getMappingUploads('financial_type_map'),
    getMappingUploads('heading_map'),
  ])

  const allUploadIds = [...ftmUploads, ...hmUploads].map(u => u.id)
  const notes = await getAdminNotes(allUploadIds)

  const saveNote = saveAdminNote.bind(null, 'mapping_upload')

  return (
    <div className="space-y-6">
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
          notes={notes}
          onSave={(uploadId, note) => saveNote(uploadId, projectId, note)}
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
          notes={notes}
          onSave={(uploadId, note) => saveNote(uploadId, projectId, note)}
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
  notes: Record<string, import('@/lib/types/database').AdminNote>
  onSave: (uploadId: string, note: string) => Promise<{ error: string | null }>
}

function MappingSection({ title, description, mappingType, projectId, uploads, notes, onSave }: MappingSectionProps) {
  return (
    <div className="space-y-4 rounded-lg border border-zinc-200 bg-white p-5">
      <div>
        <h2 className="text-sm font-semibold text-zinc-900">{title}</h2>
        <p className="mt-1 text-xs leading-relaxed text-zinc-500">{description}</p>
      </div>
      <MappingUploadForm mappingType={mappingType} projectId={projectId} />
      <div>
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-400">Recent Uploads</h3>
        <MappingUploadHistory uploads={uploads} notes={notes} onSave={onSave} />
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────
// Query logs tab
// ─────────────────────────────────────────────────────────────

async function QueryLogsSection({
  projectId,
  page,
  mode,
  type,
}: {
  projectId: string
  page: number
  mode: QueryMode | null
  type: ResponseType | null
}) {
  const filters = { mode: mode ?? undefined, type: type ?? undefined }
  const { logs, total } = await getQueryLogs(projectId, filters, page)
  const notes = await getAdminNotes(logs.map(l => l.id))

  return (
    <QueryLogsTab
      projectId={projectId}
      logs={logs}
      notes={notes}
      total={total}
      page={page}
      mode={mode}
      type={type}
    />
  )
}

// ─────────────────────────────────────────────────────────────
// Discrepancies tab
// ─────────────────────────────────────────────────────────────

async function DiscrepanciesSection({ projectId }: { projectId: string }) {
  const discrepancies = await getDiscrepancies(projectId)
  return <DiscrepanciesTab discrepancies={discrepancies} projectId={projectId} />
}
