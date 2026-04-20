'use client'

import { useMode } from '@/lib/mode-context'

export function ModeToggle() {
  const { mode, setMode } = useMode()

  return (
    <div className="flex items-center gap-1 rounded-full border border-zinc-200 bg-white p-0.5 text-xs font-medium">
      <button
        onClick={() => setMode('standard')}
        className={`rounded-full px-3 py-1 transition-colors ${
          mode === 'standard'
            ? 'bg-zinc-900 text-white'
            : 'text-zinc-500 hover:text-zinc-700'
        }`}
      >
        Standard
      </button>
      <button
        onClick={() => setMode('verbose')}
        className={`rounded-full px-3 py-1 transition-colors ${
          mode === 'verbose'
            ? 'bg-zinc-900 text-white'
            : 'text-zinc-500 hover:text-zinc-700'
        }`}
      >
        Verbose
      </button>
    </div>
  )
}
