'use client'

import type { ChatMessage, AmbiguityOption, QueryMode } from '@/lib/chat/types'
import { InterpretationBanner } from './interpretation-banner'
import { AmbiguityOptions } from './ambiguity-options'
import { ResultTable } from './result-table'

interface ChatMessageItemProps {
  message: ChatMessage
  mode: QueryMode
  isLastAssistant: boolean
  onSelectOption: (messageId: string, index: number, option: AmbiguityOption) => void
  isLoading?: boolean
}

export function ChatMessageItem({
  message,
  mode,
  isLastAssistant,
  onSelectOption,
  isLoading,
}: ChatMessageItemProps) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[70%] rounded-2xl rounded-tr-sm bg-zinc-900 px-4 py-2.5 text-sm text-white">
          {message.text}
        </div>
      </div>
    )
  }

  const { response, selected_option } = message

  return (
    <div className="flex flex-col gap-1">
      <div className="max-w-[85%] rounded-2xl rounded-tl-sm bg-white border border-zinc-200 px-4 py-3 text-sm text-zinc-800 shadow-xs">

        {response.type === 'result' && (
          <>
            <InterpretationBanner
              interpretation={response.interpretation}
              mode={mode}
              verboseTrace={response.verbose_trace}
            />
            {response.summary && (
              <p className="mb-1 text-xs text-zinc-500">{response.summary}</p>
            )}
            {response.warning && (
              <p className="mb-2 rounded-md bg-amber-50 px-3 py-1.5 text-xs text-amber-700 border border-amber-200">
                ⚠ {response.warning}
              </p>
            )}
            <ResultTable
              columns={response.columns}
              rows={response.rows}
              mode={mode}
              discrepancyWarnings={response.discrepancy_warnings}
            />
          </>
        )}

        {response.type === 'ambiguity' && (
          <>
            {Object.keys(response.interpretation).length > 0 && (
              <InterpretationBanner interpretation={response.interpretation} mode={mode} />
            )}
            <AmbiguityOptions
              prompt={response.prompt}
              options={response.options}
              onSelect={(index, option) => onSelectOption(message.id, index, option)}
              disabled={isLoading}
              selectedIndex={selected_option}
            />
          </>
        )}

        {response.type === 'missing' && (
          <>
            <InterpretationBanner interpretation={response.interpretation} mode={mode} />
            <p className="text-sm text-zinc-500">{response.message}</p>
          </>
        )}

        {response.type === 'info' && (
          <div>
            <p className="mb-2 font-medium text-zinc-800">{response.title}</p>
            <pre className="whitespace-pre-wrap font-mono text-xs text-zinc-600 leading-relaxed">
              {response.content}
            </pre>
          </div>
        )}

        {response.type === 'error' && (
          <p className="text-sm text-red-600">{response.message}</p>
        )}
      </div>
    </div>
  )
}
