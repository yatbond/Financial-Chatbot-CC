'use server'

import { auth } from '@clerk/nextjs/server'
import { revalidatePath } from 'next/cache'
import { createServerSupabase } from '@/lib/supabase/server'
import { parseCSV } from '@/lib/csv'
import type {
  AdminMappingUpload,
  MappingType,
  QueryLog,
  Discrepancy,
  AdminNote,
  AdminNoteUpsert,
  QueryMode,
  ResponseType,
} from '@/lib/types/database'
import type { ExportData, QueryLogIssue, MappingIssue, DiscrepancyNote } from '@/lib/admin/export'

export type UploadMappingState = {
  error: string | null
  success: boolean
  rowCount?: number
}

export type MappingStats = {
  financialTypeCount: number
  headingCount: number
  aliasCount: number
}

const REQUIRED_COLUMNS: Record<MappingType, string[]> = {
  financial_type_map: ['Raw_Financial_Type', 'Clean_Financial_Type'],
  heading_map: ['Data_Type', 'Friendly_Name'],
}

export async function uploadMapping(
  mappingType: MappingType,
  projectId: string,
  prevState: UploadMappingState,
  formData: FormData
): Promise<UploadMappingState> {
  const { userId } = await auth()
  if (!userId) return { error: 'Unauthorized', success: false }

  const file = formData.get('file') as File | null
  if (!file || file.size === 0) {
    return { error: 'Please select a CSV file.', success: false }
  }

  const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
  if (ext !== '.csv') {
    return { error: 'Only .csv files are supported.', success: false }
  }

  const text = await file.text()
  const { headers, rows } = parseCSV(text)

  const missing = REQUIRED_COLUMNS[mappingType].filter(col => !headers.includes(col))
  if (missing.length > 0) {
    return { error: `Missing required columns: ${missing.join(', ')}`, success: false }
  }

  if (rows.length === 0) {
    return { error: 'CSV file contains no data rows.', success: false }
  }

  let supabase: ReturnType<typeof createServerSupabase>
  try {
    supabase = createServerSupabase()
  } catch {
    return { error: 'Supabase is not configured.', success: false }
  }

  const timestamp = Date.now()
  const safeName = file.name.replace(/[^a-zA-Z0-9._-]/g, '_')
  const storagePath = `mappings/${mappingType}/${timestamp}-${safeName}`

  const fileBuffer = await file.arrayBuffer()
  const { error: storageError } = await supabase.storage
    .from('mappings')
    .upload(storagePath, fileBuffer, { contentType: 'text/csv', upsert: false })

  if (storageError) {
    return { error: `Storage upload failed: ${storageError.message}`, success: false }
  }

  const { count, error: applyError } =
    mappingType === 'financial_type_map'
      ? await applyFinancialTypeMap(supabase, rows)
      : await applyHeadingMap(supabase, rows)

  if (applyError) {
    await supabase.storage.from('mappings').remove([storagePath])
    return { error: applyError, success: false }
  }

  await supabase.from('admin_mapping_uploads').insert({
    mapping_type: mappingType,
    storage_path: storagePath,
    original_filename: file.name,
    uploaded_by: userId,
    validation_status: 'valid',
    row_count: count,
    is_applied: true,
    applied_at: new Date().toISOString(),
  })

  revalidatePath(`/projects/${projectId}/admin`)
  return { error: null, success: true, rowCount: count }
}

async function applyFinancialTypeMap(
  supabase: ReturnType<typeof createServerSupabase>,
  rows: Record<string, string>[]
): Promise<{ count: number; error: string | null }> {
  const records = rows
    .filter(r => r['Raw_Financial_Type'])
    .map(r => ({
      raw_financial_type: r['Raw_Financial_Type'],
      clean_financial_type: r['Clean_Financial_Type'] || r['Raw_Financial_Type'],
      acronyms: r['Acronyms']
        ? r['Acronyms'].split('|').map(a => a.trim().toLowerCase()).filter(Boolean)
        : [],
      is_active: true,
    }))

  if (records.length === 0) return { count: 0, error: 'No valid rows found (Raw_Financial_Type must not be empty).' }

  const { error } = await supabase
    .from('financial_type_map')
    .upsert(records, { onConflict: 'raw_financial_type' })

  if (error) return { count: 0, error: `Failed to apply financial type map: ${error.message}` }
  return { count: records.length, error: null }
}

async function applyHeadingMap(
  supabase: ReturnType<typeof createServerSupabase>,
  rows: Record<string, string>[]
): Promise<{ count: number; error: string | null }> {
  const records = rows
    .filter(r => r['Item_Code'])
    .map(r => ({
      item_code: r['Item_Code'],
      data_type: r['Data_Type'],
      friendly_name: r['Friendly_Name'] || r['Data_Type'],
      category: r['Category'] || null,
      tier: r['Tier'] !== '' && r['Tier'] != null ? parseInt(r['Tier'], 10) || null : null,
      is_active: true,
    }))

  if (records.length === 0) {
    return { count: 0, error: 'No rows with Item_Code found. Rows without Item_Code are skipped.' }
  }

  const { data: upserted, error: upsertError } = await supabase
    .from('heading_map')
    .upsert(records, { onConflict: 'item_code' })
    .select('id, item_code')

  if (upsertError) return { count: 0, error: `Failed to apply heading map: ${upsertError.message}` }

  if (upserted && upserted.length > 0) {
    const headingIds = upserted.map((h: { id: string }) => h.id)
    await supabase.from('heading_aliases').delete().in('heading_map_id', headingIds)

    const aliasMap = new Map<string, string[]>()
    for (const row of rows.filter(r => r['Item_Code'] && r['Acronyms'])) {
      const aliases = row['Acronyms'].split('|').map(a => a.trim().toLowerCase()).filter(Boolean)
      if (aliases.length > 0) aliasMap.set(row['Item_Code'], aliases)
    }

    const aliasRows = upserted.flatMap((h: { id: string; item_code: string }) =>
      (aliasMap.get(h.item_code) ?? []).map(alias => ({
        heading_map_id: h.id,
        alias,
        alias_type: 'acronym' as const,
      }))
    )

    if (aliasRows.length > 0) {
      const { error: aliasError } = await supabase.from('heading_aliases').insert(aliasRows)
      if (aliasError) {
        // Non-fatal: heading rows were applied; aliases are for query resolution only
        console.error('Failed to insert heading aliases:', aliasError.message)
      }
    }
  }

  return { count: records.length, error: null }
}

export async function getMappingUploads(mappingType: MappingType): Promise<AdminMappingUpload[]> {
  let supabase: ReturnType<typeof createServerSupabase>
  try {
    supabase = createServerSupabase()
  } catch {
    return []
  }

  const { data } = await supabase
    .from('admin_mapping_uploads')
    .select('*')
    .eq('mapping_type', mappingType)
    .order('created_at', { ascending: false })
    .limit(10)

  return (data ?? []) as AdminMappingUpload[]
}

export async function getMappingStats(): Promise<MappingStats> {
  let supabase: ReturnType<typeof createServerSupabase>
  try {
    supabase = createServerSupabase()
  } catch {
    return { financialTypeCount: 0, headingCount: 0, aliasCount: 0 }
  }

  const [ftm, hm, ha] = await Promise.all([
    supabase.from('financial_type_map').select('id', { count: 'exact', head: true }),
    supabase.from('heading_map').select('id', { count: 'exact', head: true }),
    supabase.from('heading_aliases').select('id', { count: 'exact', head: true }),
  ])

  return {
    financialTypeCount: ftm.count ?? 0,
    headingCount: hm.count ?? 0,
    aliasCount: ha.count ?? 0,
  }
}

// ─────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────

async function resolveProjectUuid(
  supabase: ReturnType<typeof createServerSupabase>,
  projectCode: string
): Promise<string | null> {
  const { data } = await supabase
    .from('projects')
    .select('id')
    .eq('project_code', projectCode)
    .single()
  return data?.id ?? null
}

// ─────────────────────────────────────────────────────────────
// Read actions
// ─────────────────────────────────────────────────────────────

export interface QueryLogFilters {
  mode?: QueryMode
  type?: ResponseType
}

export interface PaginatedQueryLogs {
  logs: QueryLog[]
  total: number
}

export async function getQueryLogs(
  projectCode: string,
  filters: QueryLogFilters,
  page: number
): Promise<PaginatedQueryLogs> {
  const PAGE_SIZE = 20
  let supabase: ReturnType<typeof createServerSupabase>
  try { supabase = createServerSupabase() } catch { return { logs: [], total: 0 } }

  const projectId = await resolveProjectUuid(supabase, projectCode)
  if (!projectId) return { logs: [], total: 0 }

  let query = supabase
    .from('query_logs')
    .select('*', { count: 'exact' })
    .eq('project_id', projectId)
    .order('created_at', { ascending: false })
    .range((page - 1) * PAGE_SIZE, page * PAGE_SIZE - 1)

  if (filters.mode) query = query.eq('mode', filters.mode)
  if (filters.type) query = query.eq('response_type', filters.type)

  const { data, count } = await query
  return { logs: (data ?? []) as QueryLog[], total: count ?? 0 }
}

export async function getDiscrepancies(projectCode: string): Promise<Discrepancy[]> {
  let supabase: ReturnType<typeof createServerSupabase>
  try { supabase = createServerSupabase() } catch { return [] }

  const projectId = await resolveProjectUuid(supabase, projectCode)
  if (!projectId) return []

  const { data } = await supabase
    .from('discrepancies')
    .select('*')
    .eq('project_id', projectId)
    .eq('review_status', 'pending')
    .order('detected_at', { ascending: false })

  return (data ?? []) as Discrepancy[]
}

export async function getAdminNotes(
  entityIds: string[]
): Promise<Record<string, AdminNote>> {
  if (entityIds.length === 0) return {}
  let supabase: ReturnType<typeof createServerSupabase>
  try { supabase = createServerSupabase() } catch { return {} }

  const { data } = await supabase
    .from('admin_notes')
    .select('*')
    .in('entity_id', entityIds)

  const result: Record<string, AdminNote> = {}
  for (const note of (data ?? []) as AdminNote[]) {
    result[note.entity_id] = note
  }
  return result
}

// ─────────────────────────────────────────────────────────────
// Write actions
// ─────────────────────────────────────────────────────────────

export async function reviewDiscrepancy(
  discrepancyId: string,
  status: 'reviewed' | 'dismissed',
  note: string,
  projectCode: string
): Promise<{ error: string | null }> {
  const { userId } = await auth()
  if (!userId) return { error: 'Unauthorized' }

  let supabase: ReturnType<typeof createServerSupabase>
  try { supabase = createServerSupabase() } catch { return { error: 'Supabase not configured' } }

  const { error } = await supabase
    .from('discrepancies')
    .update({
      review_status: status,
      reviewer_note: note.trim() || null,
      reviewed_by: userId,
      reviewed_at: new Date().toISOString(),
    })
    .eq('id', discrepancyId)

  if (error) return { error: error.message }
  revalidatePath(`/projects/${projectCode}/admin`)
  return { error: null }
}

export async function saveAdminNote(
  entityType: 'query_log' | 'mapping_upload',
  entityId: string,
  projectCode: string,
  note: string
): Promise<{ error: string | null }> {
  const { userId } = await auth()
  if (!userId) return { error: 'Unauthorized' }

  let supabase: ReturnType<typeof createServerSupabase>
  try { supabase = createServerSupabase() } catch { return { error: 'Supabase not configured' } }

  const projectId = await resolveProjectUuid(supabase, projectCode)
  if (!projectId) return { error: 'Project not found' }

  const upsertData: AdminNoteUpsert = {
    entity_type: entityType,
    entity_id: entityId,
    project_id: projectId,
    note: note.trim(),
    created_by: userId,
  }

  const { error } = await supabase
    .from('admin_notes')
    .upsert(upsertData, { onConflict: 'entity_type,entity_id' })

  if (error) return { error: error.message }
  revalidatePath(`/projects/${projectCode}/admin`)
  return { error: null }
}

export async function exportIssues(projectCode: string): Promise<ExportData | null> {
  let supabase: ReturnType<typeof createServerSupabase>
  try { supabase = createServerSupabase() } catch { return null }

  const projectId = await resolveProjectUuid(supabase, projectCode)
  if (!projectId) return null

  const { data: project } = await supabase
    .from('projects')
    .select('project_code, project_name')
    .eq('id', projectId)
    .single()

  const { data: notes } = await supabase
    .from('admin_notes')
    .select('*')
    .eq('project_id', projectId)

  const { data: discData } = await supabase
    .from('discrepancies')
    .select('*')
    .eq('project_id', projectId)
    .not('reviewer_note', 'is', null)

  const allNotes = (notes ?? []) as AdminNote[]
  const queryLogIds = allNotes.filter(n => n.entity_type === 'query_log').map(n => n.entity_id)
  const mappingUploadIds = allNotes.filter(n => n.entity_type === 'mapping_upload').map(n => n.entity_id)

  const [queryLogsData, mappingUploadsData] = await Promise.all([
    queryLogIds.length > 0
      ? supabase.from('query_logs').select('id, raw_query, response_type, mode, execution_ms, created_at').in('id', queryLogIds)
      : Promise.resolve({ data: [] }),
    mappingUploadIds.length > 0
      ? supabase.from('admin_mapping_uploads').select('id, original_filename, mapping_type, created_at').in('id', mappingUploadIds)
      : Promise.resolve({ data: [] }),
  ])

  type PartialQueryLog = Pick<QueryLog, 'id' | 'raw_query' | 'response_type' | 'mode' | 'execution_ms' | 'created_at'>
  type PartialUpload = Pick<AdminMappingUpload, 'id' | 'original_filename' | 'mapping_type' | 'created_at'>
  const queryLogMap = new Map((queryLogsData.data ?? []).map((r: PartialQueryLog) => [r.id, r]))
  const mappingUploadMap = new Map((mappingUploadsData.data ?? []).map((r: PartialUpload) => [r.id, r]))

  const queryLogIssues: QueryLogIssue[] = []
  const mappingIssues: MappingIssue[] = []

  for (const n of allNotes) {
    if (n.entity_type === 'query_log') {
      const log = queryLogMap.get(n.entity_id)
      if (log) {
        queryLogIssues.push({
          index: queryLogIssues.length + 1,
          rawQuery: log.raw_query,
          responseType: log.response_type,
          mode: log.mode,
          executionMs: log.execution_ms,
          loggedAt: log.created_at,
          adminNote: n.note,
        })
      }
    } else if (n.entity_type === 'mapping_upload') {
      const upload = mappingUploadMap.get(n.entity_id)
      if (upload) {
        mappingIssues.push({
          index: mappingIssues.length + 1,
          mappingType: upload.mapping_type,
          filename: upload.original_filename,
          uploadedAt: upload.created_at,
          adminNote: n.note,
        })
      }
    }
  }

  const discrepancyNotes: DiscrepancyNote[] = ((discData ?? []) as Discrepancy[])
    .filter(d => d.reviewer_note)
    .map((d, i) => ({
      index: i + 1,
      sheetName: d.sheet_name,
      period: `${d.report_year}-${String(d.report_month).padStart(2, '0')}`,
      dataType: d.data_type,
      itemCode: d.item_code,
      oldValue: d.old_value,
      newValue: d.new_value,
      reviewStatus: d.review_status,
      reviewerNote: d.reviewer_note!,
    }))

  return {
    projectCode: project?.project_code ?? projectCode,
    projectName: (project as { project_name?: string } | null)?.project_name ?? '',
    generatedAt: new Date().toISOString(),
    queryLogIssues,
    mappingIssues,
    discrepancyNotes,
  }
}
