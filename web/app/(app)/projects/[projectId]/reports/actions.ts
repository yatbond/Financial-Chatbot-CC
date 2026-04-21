'use server'

import { auth } from '@clerk/nextjs/server'
import { revalidatePath } from 'next/cache'
import { createServerSupabase } from '@/lib/supabase/server'
import type { ReportUpload } from '@/lib/types/database'

export type UploadReportState = {
  error: string | null
  success: boolean
  uploadId?: string
}

const ALLOWED_EXTENSIONS = ['.xls', '.xlsx']

export async function uploadReport(
  projectId: string,
  prevState: UploadReportState,
  formData: FormData
): Promise<UploadReportState> {
  const { userId } = await auth()
  if (!userId) return { error: 'Unauthorized', success: false }

  const file = formData.get('file') as File | null
  const reportMonthStr = formData.get('report_month') as string | null
  const reportYearStr = formData.get('report_year') as string | null

  if (!file || file.size === 0) {
    return { error: 'Please select a file to upload.', success: false }
  }

  const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    return { error: 'Only .xls and .xlsx files are supported.', success: false }
  }

  const reportMonth = parseInt(reportMonthStr ?? '', 10)
  const reportYear = parseInt(reportYearStr ?? '', 10)
  if (isNaN(reportMonth) || reportMonth < 1 || reportMonth > 12) {
    return { error: 'Please select a valid report month.', success: false }
  }
  if (isNaN(reportYear) || reportYear < 2000 || reportYear > 2100) {
    return { error: 'Please enter a valid report year (e.g. 2026).', success: false }
  }

  let supabase: ReturnType<typeof createServerSupabase>
  try {
    supabase = createServerSupabase()
  } catch {
    return { error: 'Supabase is not configured. Set NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.', success: false }
  }

  const { data: project, error: projectError } = await supabase
    .from('projects')
    .select('id')
    .eq('project_code', projectId)
    .single()

  if (projectError || !project) {
    return { error: 'Project not found.', success: false }
  }

  const monthPadded = String(reportMonth).padStart(2, '0')
  const timestamp = Date.now()
  const safeName = file.name.replace(/[^a-zA-Z0-9._-]/g, '_')
  const storagePath = `reports/${project.id}/${reportYear}-${monthPadded}/${timestamp}-${safeName}`

  const fileBuffer = await file.arrayBuffer()
  const { error: storageError } = await supabase.storage
    .from('reports')
    .upload(storagePath, fileBuffer, {
      contentType: file.type || 'application/octet-stream',
      upsert: false,
    })

  if (storageError) {
    return { error: `Storage upload failed: ${storageError.message}`, success: false }
  }

  const { data: upload, error: insertError } = await supabase
    .from('report_uploads')
    .insert({
      project_id: project.id,
      report_month: reportMonth,
      report_year: reportYear,
      storage_path: storagePath,
      original_filename: file.name,
      uploaded_by: userId,
    })
    .select('id')
    .single()

  if (insertError) {
    await supabase.storage.from('reports').remove([storagePath])
    return { error: `Failed to save upload record: ${insertError.message}`, success: false }
  }

  // Phase 5 placeholder: trigger ingestion worker for upload.id

  revalidatePath(`/projects/${projectId}/reports`)
  return { error: null, success: true, uploadId: upload.id }
}

export async function getReportUploads(projectId: string): Promise<ReportUpload[]> {
  let supabase: ReturnType<typeof createServerSupabase>
  try {
    supabase = createServerSupabase()
  } catch {
    return []
  }

  const { data: project } = await supabase
    .from('projects')
    .select('id')
    .eq('project_code', projectId)
    .single()

  if (!project) return []

  const { data } = await supabase
    .from('report_uploads')
    .select('*')
    .eq('project_id', project.id)
    .order('created_at', { ascending: false })

  return data ?? []
}

