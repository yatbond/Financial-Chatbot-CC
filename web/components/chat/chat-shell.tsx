'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import type {
  ChatMessage,
  SessionContext,
  AmbiguityOption,
  ChatResponse,
  AmbiguityResponse,
  ChatRequest,
} from '@/lib/chat/types'
import { ChatInput } from './chat-input'
import { ChatMessageItem } from './chat-message-item'
import { ContextStrip } from './context-strip'
import { useMode } from '@/lib/mode-context'

interface ChatShellProps {
  projectId: string
  projectCode?: string
  projectName?: string
  period?: string
}

let idCounter = 0
function nextId() { return String(++idCounter) }

export function ChatShell({ projectId, projectCode, projectName, period }: ChatShellProps) {
  const { mode } = useMode()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(false)
  const [context, setContext] = useState<SessionContext>({
    project_code: projectCode,
    project_name: projectName,
    period: period ?? 'Feb 2026',
  })

  const bottomRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const applyContextUpdate = useCallback(
    (update: Partial<SessionContext> | undefined) => {
      if (!update) return
      setContext((prev) => ({ ...prev, ...update }))
    },
    []
  )

  async function postQuery(body: ChatRequest): Promise<ChatResponse> {
    const res = await fetch(`/api/projects/${projectId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      return { type: 'error', message: err.message ?? 'Request failed.' }
    }
    return res.json()
  }

  async function handleSubmit(query: string) {
    const userMsg: ChatMessage = { id: nextId(), role: 'user', text: query }
    setMessages((prev) => [...prev, userMsg])
    setLoading(true)

    const body: ChatRequest = { query, context, mode }
    const response = await postQuery(body)

    const assistantMsg: ChatMessage = {
      id: nextId(),
      role: 'assistant',
      query,
      response,
    }
    setMessages((prev) => [...prev, assistantMsg])
    setLoading(false)

    if (response.type === 'result' || response.type === 'ambiguity') {
      applyContextUpdate(response.context_update)
    }
  }

  async function handleOptionSelect(
    messageId: string,
    optionIndex: number,
    option: AmbiguityOption
  ) {
    // Mark the option as selected in the assistant message
    setMessages((prev) =>
      prev.map((m) =>
        m.id === messageId && m.role === 'assistant'
          ? { ...m, selected_option: optionIndex }
          : m
      )
    )

    // Build context with selected params merged in
    const mergedContext: SessionContext = { ...context, ...option.params }

    // Get the original query from the assistant message
    const assistantMsg = messages.find((m) => m.id === messageId)
    const originalQuery = assistantMsg?.role === 'assistant' ? assistantMsg.query : ''

    // Get the prior ambiguity options from that message
    const priorOptions =
      assistantMsg?.role === 'assistant' && assistantMsg.response.type === 'ambiguity'
        ? (assistantMsg.response as AmbiguityResponse).options
        : undefined

    setLoading(true)

    const body: ChatRequest = {
      query: originalQuery,
      context: mergedContext,
      mode,
      selected_option_index: optionIndex,
      prior_options: priorOptions,
    }
    const response = await postQuery(body)

    const followupMsg: ChatMessage = {
      id: nextId(),
      role: 'assistant',
      query: option.label,
      response,
    }
    setMessages((prev) => [...prev, followupMsg])
    setLoading(false)

    if (response.type === 'result' || response.type === 'ambiguity') {
      applyContextUpdate(response.context_update)
    }
  }

  const lastAssistantId = [...messages].reverse().find((m) => m.role === 'assistant')?.id

  return (
    <div className="flex h-full flex-col">
      <ContextStrip context={context} />

      {/* Thread */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-center">
            <div className="rounded-full bg-zinc-100 p-3">
              <svg className="h-6 w-6 text-zinc-400" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z" />
              </svg>
            </div>
            <div>
              <h2 className="text-sm font-medium text-zinc-700">Ask about your financial reports</h2>
              <p className="mt-1 max-w-sm text-xs text-zinc-400">
                Try: <span className="font-mono">projected gp</span> · <span className="font-mono">trend prelim 6</span> · <span className="font-mono">shortcut</span>
              </p>
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <ChatMessageItem
            key={msg.id}
            message={msg}
            mode={mode}
            isLastAssistant={msg.id === lastAssistantId}
            onSelectOption={handleOptionSelect}
            isLoading={loading}
          />
        ))}

        {loading && (
          <div className="flex items-center gap-2">
            <div className="flex gap-1">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="h-1.5 w-1.5 rounded-full bg-zinc-400 animate-bounce"
                  style={{ animationDelay: `${i * 0.15}s` }}
                />
              ))}
            </div>
            <span className="text-xs text-zinc-400">Resolving…</span>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <ChatInput onSubmit={handleSubmit} disabled={loading} />
    </div>
  )
}
