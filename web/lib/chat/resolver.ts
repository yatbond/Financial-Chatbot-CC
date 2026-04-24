// Real query resolver — delegates to the Python ingestion service /query endpoint.
// Replaces the Phase 9 mock. Requires INGESTION_SERVICE_URL env var.

import type { ChatRequest, ChatResponse } from './types'

export async function resolveQuery(
  req: ChatRequest,
  projectUuid: string,
): Promise<ChatResponse> {
  const ingestionUrl = process.env.INGESTION_SERVICE_URL
  if (!ingestionUrl) {
    return {
      type: 'error',
      message: 'Query service is not configured. Set INGESTION_SERVICE_URL.',
    }
  }

  const body = {
    query: req.query,
    project_id: projectUuid,
    context: req.context ?? {},
    mode: req.mode ?? 'standard',
    selected_option_index: req.selected_option_index ?? null,
    prior_options: req.prior_options ?? null,
  }

  let res: Response
  try {
    res = await fetch(`${ingestionUrl}/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    return { type: 'error', message: 'Could not reach query service.' }
  }

  if (!res.ok) {
    return { type: 'error', message: `Query service error (HTTP ${res.status}).` }
  }

  return res.json() as Promise<ChatResponse>
}
