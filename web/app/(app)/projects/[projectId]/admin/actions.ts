'use server'

import { auth } from '@clerk/nextjs/server'
import { revalidatePath } from 'next/cache'
import { createServerSupabase } from '@/lib/supabase/server'
import { parseCSV } from '@/lib/csv'
import type { AdminMappingUpload, MappingType } from '@/lib/types/database'

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
