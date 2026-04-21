'use client'

import { useActionState, useRef } from 'react'
import { uploadMapping, type UploadMappingState } from '@/app/(app)/projects/[projectId]/admin/actions'
import { Button } from '@/components/ui/button'
import type { MappingType } from '@/lib/types/database'

interface MappingUploadFormProps {
  mappingType: MappingType
  projectId: string
}

const initialState: UploadMappingState = { error: null, success: false }

export function MappingUploadForm({ mappingType, projectId }: MappingUploadFormProps) {
  const uploadWithArgs = uploadMapping.bind(null, mappingType, projectId)
  const [state, formAction, isPending] = useActionState(uploadWithArgs, initialState)
  const formRef = useRef<HTMLFormElement>(null)

  if (state.success) {
    return (
      <div className="rounded-lg border border-green-200 bg-green-50 p-3">
        <div className="flex items-center gap-1.5 text-xs font-medium text-green-800">
          <svg className="h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
          </svg>
          Applied — {state.rowCount} rows processed
        </div>
        <button
          type="button"
          className="mt-2 text-xs font-medium text-green-800 underline underline-offset-2 hover:text-green-900"
          onClick={() => formRef.current?.reset()}
        >
          Upload another file
        </button>
      </div>
    )
  }

  return (
    <form ref={formRef} action={formAction} className="space-y-2.5">
      <div>
        <input
          name="file"
          type="file"
          accept=".csv,text/csv"
          required
          disabled={isPending}
          className="w-full rounded-lg border border-zinc-200 bg-white px-2.5 py-1.5 text-sm text-zinc-900 outline-none file:mr-2 file:rounded file:border-0 file:bg-zinc-100 file:px-2 file:py-0.5 file:text-xs file:font-medium file:text-zinc-700 hover:file:bg-zinc-200 focus:border-zinc-400 focus:ring-2 focus:ring-zinc-200 disabled:opacity-50"
        />
        <p className="mt-1 text-xs text-zinc-400">.csv files only</p>
      </div>

      {state.error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {state.error}
        </div>
      )}

      <Button type="submit" disabled={isPending} size="sm" className="w-full">
        {isPending ? (
          <span className="flex items-center gap-1.5">
            <svg className="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Uploading & applying…
          </span>
        ) : (
          'Upload & Apply'
        )}
      </Button>
    </form>
  )
}
