import type { SessionContext } from '@/lib/chat/types'

interface ContextStripProps {
  context: SessionContext
}

export function ContextStrip({ context }: ContextStripProps) {
  const chips: { label: string; value: string }[] = []

  if (context.project_code && context.project_name) {
    chips.push({ label: 'Project', value: `${context.project_code} / ${context.project_name}` })
  } else if (context.project_code) {
    chips.push({ label: 'Project', value: context.project_code })
  }
  if (context.period) chips.push({ label: 'Period', value: context.period })
  if (context.sheet_name) chips.push({ label: 'Sheet', value: context.sheet_name })
  if (context.financial_type) chips.push({ label: 'Fin. Type', value: context.financial_type })
  if (context.data_type) chips.push({ label: 'Data Type', value: context.data_type })

  if (chips.length === 0) return null

  return (
    <div className="flex flex-wrap items-center gap-1.5 px-4 py-1.5 border-b border-zinc-100 bg-zinc-50/60">
      <span className="text-[10px] font-medium uppercase tracking-wide text-zinc-400 mr-1">Context</span>
      {chips.map((chip) => (
        <span
          key={chip.label}
          className="inline-flex items-center gap-1 rounded-full border border-zinc-200 bg-white px-2 py-0.5 text-[10px] text-zinc-600"
        >
          <span className="text-zinc-400">{chip.label}:</span>
          <span className="font-medium">{chip.value}</span>
        </span>
      ))}
    </div>
  )
}
