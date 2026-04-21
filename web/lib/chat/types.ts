// Chat system types for Phase 10.
// The API route returns ChatResponse; the UI renders it.
export type QueryMode = 'standard' | 'verbose'

// ─── Session context ────────────────────────────────────────────────────────
export interface SessionContext {
  project_code?: string
  project_name?: string
  period?: string          // e.g. "Feb 2026"
  sheet_name?: string
  financial_type?: string
  data_type?: string
  last_shortcut?: string
}

// ─── Resolved interpretation ─────────────────────────────────────────────────
export interface ResolvedParams {
  project?: string
  sheet_name?: string
  financial_type?: string
  data_type?: string
  period?: string
  shortcut?: string
  months?: number
}

// ─── Ambiguity option ────────────────────────────────────────────────────────
export interface AmbiguityOption {
  label: string
  params: Partial<ResolvedParams>
}

// ─── Result table ────────────────────────────────────────────────────────────
export type ResultRow = Record<string, string | number | null>

// ─── Verbose trace (per-query source traceability) ───────────────────────────
export interface VerboseTrace {
  row_number: number | null
  cell_reference: string | null
  upload_timestamp: string | null
  source_workbook: string | null
}

// ─── Discrepancy warning (superseded value on a result row) ──────────────────
export interface DiscrepancyWarning {
  item: string
  old_value: number
  new_value: number
  superseded_by_upload_id: string
}

// ─── API responses ───────────────────────────────────────────────────────────
export interface ResultResponse {
  type: 'result'
  interpretation: ResolvedParams
  columns: string[]
  rows: ResultRow[]
  summary?: string
  warning?: string
  context_update?: Partial<SessionContext>
  verbose_trace?: VerboseTrace
  discrepancy_warnings?: DiscrepancyWarning[]
}

export interface AmbiguityResponse {
  type: 'ambiguity'
  interpretation: Partial<ResolvedParams>
  prompt: string
  options: AmbiguityOption[]
  context_update?: Partial<SessionContext>
}

export interface MissingResponse {
  type: 'missing'
  interpretation: Partial<ResolvedParams>
  message: string
}

export interface InfoResponse {
  type: 'info'
  title: string
  content: string   // markdown-safe plain text
}

export interface ErrorResponse {
  type: 'error'
  message: string
}

export type ChatResponse =
  | ResultResponse
  | AmbiguityResponse
  | MissingResponse
  | InfoResponse
  | ErrorResponse

// ─── Chat message (local UI state) ──────────────────────────────────────────
export interface UserMessage {
  id: string
  role: 'user'
  text: string
}

export interface AssistantMessage {
  id: string
  role: 'assistant'
  query: string
  response: ChatResponse
  // set after user picks an ambiguity option
  selected_option?: number
}

export type ChatMessage = UserMessage | AssistantMessage

// ─── API request body ────────────────────────────────────────────────────────
export interface ChatRequest {
  query: string
  context: SessionContext
  mode?: QueryMode
  // if set, the user picked option N from a prior ambiguity response
  selected_option_index?: number
  // the ambiguity options from the prior turn (so resolver can re-use params)
  prior_options?: AmbiguityOption[]
}
