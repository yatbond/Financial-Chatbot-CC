export interface QueryLogIssue {
  index: number
  rawQuery: string
  responseType: string | null
  mode: string
  executionMs: number | null
  loggedAt: string
  adminNote: string
}

export interface MappingIssue {
  index: number
  mappingType: string
  filename: string
  uploadedAt: string
  adminNote: string
}

export interface DiscrepancyNote {
  index: number
  sheetName: string
  period: string
  dataType: string | null
  itemCode: string | null
  oldValue: number | null
  newValue: number | null
  reviewStatus: string
  reviewerNote: string
}

export interface ExportData {
  projectCode: string
  projectName: string
  generatedAt: string
  queryLogIssues: QueryLogIssue[]
  mappingIssues: MappingIssue[]
  discrepancyNotes: DiscrepancyNote[]
}

export function buildExportMarkdown(data: ExportData): string {
  const lines: string[] = [
    `# Admin Issues Export — Project: ${data.projectCode} ${data.projectName}`,
    `# Generated: ${data.generatedAt}`,
    `# Usage: paste this file into Claude Code and ask it to fix the issues below.`,
  ]

  if (data.queryLogIssues.length > 0) {
    lines.push('', `## Query Log Issues (${data.queryLogIssues.length})`)
    for (const q of data.queryLogIssues) {
      lines.push(
        '',
        `### [QL-${q.index}] ${q.responseType ?? 'unknown'} — "${q.rawQuery}"`,
        `- raw_query: "${q.rawQuery}"`,
        `- response_type: ${q.responseType ?? 'null'} | mode: ${q.mode} | execution_ms: ${q.executionMs ?? 'null'}`,
        `- logged_at: ${q.loggedAt}`,
        `- admin_note: "${q.adminNote}"`,
        `- relevant_files: web/lib/chat/resolver.ts, web/lib/chat/types.ts`,
      )
    }
  }

  if (data.mappingIssues.length > 0) {
    lines.push('', `## Mapping Issues (${data.mappingIssues.length})`)
    for (const m of data.mappingIssues) {
      lines.push(
        '',
        `### [MAP-${m.index}] ${m.mappingType} — ${m.filename}`,
        `- mapping_type: ${m.mappingType}`,
        `- uploaded_at: ${m.uploadedAt}`,
        `- admin_note: "${m.adminNote}"`,
        `- relevant_files: web/app/(app)/projects/[projectId]/admin/actions.ts, web/lib/chat/resolver.ts`,
      )
    }
  }

  if (data.discrepancyNotes.length > 0) {
    lines.push('', `## Discrepancy Notes (${data.discrepancyNotes.length})`)
    for (const d of data.discrepancyNotes) {
      lines.push(
        '',
        `### [DISC-${d.index}] ${d.sheetName} — ${d.period} — ${d.dataType ?? d.itemCode ?? 'unknown'}`,
        `- sheet: ${d.sheetName} | period: ${d.period} | item_code: ${d.itemCode ?? 'null'}`,
        `- old_value: ${d.oldValue ?? 'null'} | new_value: ${d.newValue ?? 'null'}`,
        `- review_status: ${d.reviewStatus}`,
        `- reviewer_note: "${d.reviewerNote}"`,
        `- relevant_files: web/supabase/migrations/20260421000001_initial_schema.sql, web/lib/chat/resolver.ts`,
      )
    }
  }

  return lines.join('\n')
}
