'use client'

import type { AmbiguityOption } from '@/lib/chat/types'

interface AmbiguityOptionsProps {
  prompt: string
  options: AmbiguityOption[]
  onSelect: (index: number, option: AmbiguityOption) => void
  disabled?: boolean
  selectedIndex?: number
}

export function AmbiguityOptions({
  prompt,
  options,
  onSelect,
  disabled,
  selectedIndex,
}: AmbiguityOptionsProps) {
  return (
    <div className="mt-2 space-y-2">
      <p className="text-sm text-zinc-600">{prompt}</p>
      <div className="flex flex-wrap gap-2">
        {options.map((opt, i) => {
          const isSelected = selectedIndex === i
          return (
            <button
              key={i}
              onClick={() => onSelect(i, opt)}
              disabled={disabled || selectedIndex !== undefined}
              className={[
                'rounded-md border px-3 py-1.5 text-xs font-medium transition-colors',
                isSelected
                  ? 'border-zinc-900 bg-zinc-900 text-white'
                  : 'border-zinc-300 bg-white text-zinc-700 hover:border-zinc-500 hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-50',
              ].join(' ')}
            >
              {opt.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}
