'use client'

import { useState, useTransition } from 'react'
import { exportIssues } from '@/app/(app)/projects/[projectId]/admin/actions'
import { buildExportMarkdown } from '@/lib/admin/export'

interface ExportButtonProps {
  projectId: string
}

export function ExportButton({ projectId }: ExportButtonProps) {
  const [isPending, startTransition] = useTransition()
  const [error, setError] = useState<string | null>(null)

  function handleExport() {
    setError(null)
    startTransition(async () => {
      const data = await exportIssues(projectId)
      if (!data) {
        setError('Export failed — project not found.')
        return
      }
      const md = buildExportMarkdown(data)
      const blob = new Blob([md], { type: 'text/markdown' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      const date = new Date().toISOString().slice(0, 10)
      a.href = url
      a.download = `admin-issues-${date}.md`
      a.click()
      URL.revokeObjectURL(url)
    })
  }

  return (
    <div>
      <button
        type="button"
        onClick={handleExport}
        disabled={isPending}
        className="rounded border border-zinc-200 bg-white px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"
      >
        {isPending ? 'Exporting…' : 'Export for Claude'}
      </button>
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  )
}
