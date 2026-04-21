'use client'

import { useActionState, useRef } from 'react'
import { uploadReport, type UploadReportState } from '@/app/(app)/projects/[projectId]/reports/actions'
import { Button } from '@/components/ui/button'

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

const currentYear = new Date().getFullYear()
const YEARS = Array.from({ length: 5 }, (_, i) => currentYear - 2 + i)

interface ReportUploadFormProps {
  projectId: string
}

const initialState: UploadReportState = { error: null, success: false }

export function ReportUploadForm({ projectId }: ReportUploadFormProps) {
  const uploadWithProject = uploadReport.bind(null, projectId)
  const [state, formAction, isPending] = useActionState(uploadWithProject, initialState)
  const formRef = useRef<HTMLFormElement>(null)

  if (state.success) {
    return (
      <div className="rounded-lg border border-green-200 bg-green-50 p-4">
        <div className="flex items-center gap-2 text-sm font-medium text-green-800">
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
          </svg>
          Report uploaded successfully
        </div>
        <p className="mt-1 text-xs text-green-700">
          The file has been stored and is queued for ingestion processing.
        </p>
        <button
          className="mt-3 text-xs font-medium text-green-800 underline underline-offset-2 hover:text-green-900"
          onClick={() => formRef.current?.reset()}
          type="button"
        >
          Upload another report
        </button>
      </div>
    )
  }

  return (
    <form ref={formRef} action={formAction} className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <label htmlFor="report_month" className="text-xs font-medium text-zinc-700">
            Report Month
          </label>
          <select
            id="report_month"
            name="report_month"
            required
            defaultValue=""
            className="w-full rounded-lg border border-zinc-200 bg-white px-2.5 py-1.5 text-sm text-zinc-900 outline-none focus:border-zinc-400 focus:ring-2 focus:ring-zinc-200 disabled:opacity-50"
            disabled={isPending}
          >
            <option value="" disabled>Select month</option>
            {MONTHS.map((name, i) => (
              <option key={i + 1} value={i + 1}>{name}</option>
            ))}
          </select>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="report_year" className="text-xs font-medium text-zinc-700">
            Report Year
          </label>
          <select
            id="report_year"
            name="report_year"
            required
            defaultValue=""
            className="w-full rounded-lg border border-zinc-200 bg-white px-2.5 py-1.5 text-sm text-zinc-900 outline-none focus:border-zinc-400 focus:ring-2 focus:ring-zinc-200 disabled:opacity-50"
            disabled={isPending}
          >
            <option value="" disabled>Select year</option>
            {YEARS.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="space-y-1.5">
        <label htmlFor="file" className="text-xs font-medium text-zinc-700">
          Excel File
        </label>
        <input
          id="file"
          name="file"
          type="file"
          required
          accept=".xls,.xlsx,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          disabled={isPending}
          className="w-full rounded-lg border border-zinc-200 bg-white px-2.5 py-1.5 text-sm text-zinc-900 outline-none file:mr-2 file:rounded file:border-0 file:bg-zinc-100 file:px-2 file:py-0.5 file:text-xs file:font-medium file:text-zinc-700 hover:file:bg-zinc-200 focus:border-zinc-400 focus:ring-2 focus:ring-zinc-200 disabled:opacity-50"
        />
        <p className="text-xs text-zinc-400">.xls and .xlsx files only</p>
      </div>

      {state.error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {state.error}
        </div>
      )}

      <Button type="submit" disabled={isPending} className="w-full">
        {isPending ? (
          <span className="flex items-center gap-2">
            <svg className="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Uploading…
          </span>
        ) : (
          'Upload Report'
        )}
      </Button>
    </form>
  )
}
