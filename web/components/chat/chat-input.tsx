'use client'

import { useRef, type FormEvent, type KeyboardEvent } from 'react'

interface ChatInputProps {
  onSubmit: (query: string) => void
  disabled?: boolean
}

export function ChatInput({ onSubmit, disabled }: ChatInputProps) {
  const ref = useRef<HTMLTextAreaElement>(null)

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const val = ref.current?.value.trim()
    if (!val) return
    onSubmit(val)
    if (ref.current) ref.current.value = ''
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      const val = ref.current?.value.trim()
      if (!val) return
      onSubmit(val)
      if (ref.current) ref.current.value = ''
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-end gap-2 border-t border-zinc-200 bg-white px-4 py-3">
      <textarea
        ref={ref}
        rows={1}
        disabled={disabled}
        onKeyDown={handleKeyDown}
        placeholder="projected gp  ·  trend prelim 6  ·  shortcut"
        className="flex-1 resize-none rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-zinc-500 focus:outline-none focus:ring-2 focus:ring-zinc-200 disabled:opacity-50"
        style={{ minHeight: '38px', maxHeight: '120px' }}
        onInput={(e) => {
          const el = e.currentTarget
          el.style.height = 'auto'
          el.style.height = `${Math.min(el.scrollHeight, 120)}px`
        }}
      />
      <button
        type="submit"
        disabled={disabled}
        className="shrink-0 rounded-lg bg-zinc-900 px-3 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-40 transition-colors"
      >
        Send
      </button>
    </form>
  )
}
