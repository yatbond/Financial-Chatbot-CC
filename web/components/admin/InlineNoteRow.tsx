'use client'

import { useState, useTransition } from 'react'

interface NoteProps {
  existingNote: string | null
  onSave: (note: string) => Promise<{ error: string | null }>
  colSpan: number
}

interface NoteCellProps {
  hasNote: boolean
  isOpen: boolean
  onToggle: () => void
}

export function NoteCell({ hasNote, isOpen, onToggle }: NoteCellProps) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="text-xs text-zinc-400 transition-colors hover:text-zinc-700"
    >
      {isOpen ? 'Cancel' : hasNote ? '📝 Edit note' : '+ Note'}
    </button>
  )
}

export function NoteExpandRow({
  existingNote,
  onSave,
  colSpan,
  onClose,
  asDiv = false,
}: NoteProps & { onClose: () => void; asDiv?: boolean }) {
  const [text, setText] = useState(existingNote ?? '')
  const [isPending, startTransition] = useTransition()
  const [error, setError] = useState<string | null>(null)

  function handleSave() {
    startTransition(async () => {
      const result = await onSave(text)
      if (result.error) {
        setError(result.error)
      } else {
        onClose()
      }
    })
  }

  const inner = (
    <>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={2}
        placeholder="Note for Claude Code (e.g. 'query returned wrong type — should resolve to shortcut 3')"
        className="w-full resize-none rounded border border-amber-200 bg-white px-2 py-1.5 text-xs text-zinc-800 placeholder:text-zinc-400 focus:border-amber-400 focus:outline-none"
      />
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
      <div className="mt-1.5 flex gap-2">
        <button
          type="button"
          onClick={handleSave}
          disabled={isPending || !text.trim()}
          className="rounded bg-zinc-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
        >
          {isPending ? 'Saving…' : 'Save note'}
        </button>
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-zinc-200 bg-white px-3 py-1 text-xs text-zinc-600"
        >
          Cancel
        </button>
      </div>
    </>
  )

  if (asDiv) return <div>{inner}</div>

  return (
    <tr className="bg-amber-50">
      <td colSpan={colSpan} className="px-3 py-2">
        {inner}
      </td>
    </tr>
  )
}
