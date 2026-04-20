'use client'

import { useMode } from '@/lib/mode-context'
import { ModeToggle } from './mode-toggle'

interface ContextBarProps {
  projectCode?: string
  projectName?: string
  period?: string
}

export function ContextBar({ projectCode, projectName, period }: ContextBarProps) {
  const { mode } = useMode()

  return (
    <div className="flex items-center justify-between border-b border-zinc-200 bg-white px-4 py-2 text-xs">
      <div className="flex items-center gap-4 text-zinc-600">
        {projectCode && projectName ? (
          <span className="font-medium text-zinc-900">
            {projectCode} / {projectName}
          </span>
        ) : (
          <span className="text-zinc-400">No project selected</span>
        )}
        {period && (
          <>
            <span className="text-zinc-300">|</span>
            <span>{period}</span>
          </>
        )}
        <span className="text-zinc-300">|</span>
        <span className={mode === 'verbose' ? 'font-medium text-amber-600' : 'text-zinc-500'}>
          {mode === 'verbose' ? 'Verbose' : 'Standard'} mode
        </span>
      </div>
      <ModeToggle />
    </div>
  )
}
