import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'
import { resolveQuery } from '@/lib/chat/resolver'
import { createServerSupabase } from '@/lib/supabase/server'
import type { ChatRequest, ChatResponse } from '@/lib/chat/types'
import type { QueryLogInsert, ResponseType } from '@/lib/types/database'

function toResponseType(res: ChatResponse): ResponseType | null {
  if (res.type === 'ambiguity') return 'ambiguity'
  if (res.type === 'missing') return 'missing'
  if (res.type === 'error') return 'error'
  if (res.type === 'info') return null
  if (res.type === 'result') {
    const shortcut = res.interpretation.shortcut
    if (shortcut === 'trend') return 'trend'
    if (shortcut === 'compare') return 'compare'
    if (shortcut === 'total') return 'total'
    if (shortcut === 'detail') return 'detail'
    if (shortcut === 'risk') return 'risk'
    if (shortcut === 'cash flow') return 'cash_flow'
    if (shortcut === 'list') return 'list'
    if (shortcut === 'analyze' || shortcut === 'analyse') return 'table'
    return res.rows.length > 1 ? 'table' : 'value'
  }
  return null
}

async function insertQueryLog(
  projectId: string,
  body: ChatRequest,
  response: ChatResponse,
  executionMs: number,
  userId: string,
): Promise<void> {
  const supabase = createServerSupabase()
  const interp: Partial<{
    sheet_name: string
    financial_type: string
    data_type: string
    shortcut: string
  }> = (response.type === 'result' || response.type === 'ambiguity' || response.type === 'missing')
    ? response.interpretation
    : {}

  const log: QueryLogInsert = {
    project_id: projectId,
    user_id: userId,
    raw_query: body.query,
    resolved_sheet_name: interp.sheet_name ?? null,
    resolved_financial_type: interp.financial_type ?? null,
    resolved_data_type: interp.data_type ?? null,
    resolved_item_code: null,
    resolved_month: null,
    resolved_year: null,
    resolved_shortcut: interp.shortcut ?? null,
    interpretation_options: response.type === 'ambiguity'
      ? response.options.map(o => ({ label: o.label, params: o.params as Record<string, string | number | undefined> }))
      : null,
    selected_option_index: body.selected_option_index ?? null,
    was_ambiguous: response.type === 'ambiguity',
    mode: body.mode ?? 'standard',
    response_type: toResponseType(response),
    execution_ms: executionMs,
  }

  await supabase.from('query_logs').insert(log)
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ projectId: string }> }
) {
  const { projectId } = await params

  let body: ChatRequest
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ type: 'error', message: 'Invalid request body.' }, { status: 400 })
  }

  if (!body.query?.trim()) {
    return NextResponse.json({ type: 'error', message: 'Query is required.' }, { status: 400 })
  }

  if (!body.context) body.context = {}
  if (!body.context.project_code) body.context.project_code = projectId

  const startMs = Date.now()

  let response: ChatResponse
  try {
    response = resolveQuery(body)
  } catch (err) {
    console.error('[chat/route] resolver error', err)
    return NextResponse.json({ type: 'error', message: 'Query resolution failed.' }, { status: 500 })
  }

  const executionMs = Date.now() - startMs

  // Fire-and-forget — never let logging break the response
  try {
    const { userId } = await auth()
    await insertQueryLog(projectId, body, response, executionMs, userId ?? 'anon')
  } catch (err) {
    console.warn('[chat/route] query_log insert failed (non-fatal)', err)
  }

  return NextResponse.json(response)
}
