// Database types for the Financial Chatbot Web App.
// Mirrors the Supabase Postgres schema defined in:
//   web/supabase/migrations/20260421000001_initial_schema.sql
//
// These are hand-authored for Phase 1. Once the Supabase CLI is fully
// configured, replace with generated types via:
//   npx supabase gen types typescript --project-id <id> > lib/types/supabase.ts

// ─────────────────────────────────────────────────────────────
// Shared
// ─────────────────────────────────────────────────────────────

export type ValidationStatus = 'pending' | 'valid' | 'partial' | 'invalid'
export type ParseStatus = 'pending' | 'ok' | 'partial' | 'error' | 'skipped'
export type ReviewStatus = 'pending' | 'reviewed' | 'dismissed'
export type MappingType = 'financial_type_map' | 'heading_map'
export type ProjectRole = 'member' | 'admin'
export type QueryMode = 'standard' | 'verbose'
export type AliasType = 'acronym' | 'synonym' | 'shorthand'

export type ResponseType =
  | 'value'
  | 'table'
  | 'trend'
  | 'compare'
  | 'total'
  | 'detail'
  | 'risk'
  | 'cash_flow'
  | 'list'
  | 'ambiguity'
  | 'missing'
  | 'error'

// ─────────────────────────────────────────────────────────────
// projects
// ─────────────────────────────────────────────────────────────

export interface Project {
  id: string
  project_code: string
  project_name: string
  created_at: string
  updated_at: string
}

export type ProjectInsert = Omit<Project, 'id' | 'created_at' | 'updated_at'>
export type ProjectUpdate = Partial<ProjectInsert>

// ─────────────────────────────────────────────────────────────
// project_members
// ─────────────────────────────────────────────────────────────

export interface ProjectMember {
  id: string
  project_id: string
  user_id: string       // Clerk user ID
  role: ProjectRole
  created_at: string
}

export type ProjectMemberInsert = Omit<ProjectMember, 'id' | 'created_at'>
export type ProjectMemberUpdate = Pick<ProjectMember, 'role'>

// ─────────────────────────────────────────────────────────────
// report_uploads
// ─────────────────────────────────────────────────────────────

export interface ReportUpload {
  id: string
  project_id: string
  report_month: number          // 1–12
  report_year: number
  storage_path: string          // Supabase Storage path
  original_filename: string
  uploaded_by: string           // Clerk user ID
  upload_timestamp: string
  validation_status: ValidationStatus
  is_active: boolean
  unmapped_heading_count: number
  unmapped_financial_type_count: number
  overlap_count: number
  ingestion_error: string | null
  created_at: string
  updated_at: string
}

export type ReportUploadInsert = Omit<
  ReportUpload,
  | 'id'
  | 'upload_timestamp'
  | 'validation_status'
  | 'is_active'
  | 'unmapped_heading_count'
  | 'unmapped_financial_type_count'
  | 'overlap_count'
  | 'ingestion_error'
  | 'created_at'
  | 'updated_at'
>

export type ReportUploadUpdate = Partial<
  Pick<
    ReportUpload,
    | 'validation_status'
    | 'is_active'
    | 'unmapped_heading_count'
    | 'unmapped_financial_type_count'
    | 'overlap_count'
    | 'ingestion_error'
  >
>

// ─────────────────────────────────────────────────────────────
// report_sheet_metadata
// ─────────────────────────────────────────────────────────────

export interface ReportSheetMetadata {
  id: string
  upload_id: string
  sheet_name: string
  row_count: number | null
  mapped_row_count: number | null
  unmapped_row_count: number | null
  parse_status: ParseStatus
  parse_error: string | null
  created_at: string
}

export type ReportSheetMetadataInsert = Omit<ReportSheetMetadata, 'id' | 'created_at'>

// ─────────────────────────────────────────────────────────────
// normalized_financial_rows
// ─────────────────────────────────────────────────────────────

export interface NormalizedFinancialRow {
  id: string
  upload_id: string
  project_id: string
  sheet_name: string
  report_month: number      // 1–12
  report_year: number

  // Financial type resolution
  raw_financial_type: string | null
  financial_type: string | null     // canonical clean name

  // Heading resolution
  item_code: string | null
  data_type: string | null          // canonical data_type
  friendly_name: string | null      // official Friendly_Name
  category: string | null           // 'Income', 'Cost', etc.
  tier: number | null

  // Value
  value: number | null

  // Verbose-mode traceability
  source_row_number: number | null
  source_cell_reference: string | null  // e.g. 'C15'

  // Active-truth tracking
  is_active: boolean
  superseded_by_upload_id: string | null

  created_at: string
}

export type NormalizedFinancialRowInsert = Omit<NormalizedFinancialRow, 'id' | 'created_at'>

// ─────────────────────────────────────────────────────────────
// financial_type_map
// ─────────────────────────────────────────────────────────────

export interface FinancialTypeMap {
  id: string
  raw_financial_type: string
  clean_financial_type: string
  acronyms: string[]
  is_active: boolean
  created_at: string
  updated_at: string
}

export type FinancialTypeMapInsert = Omit<FinancialTypeMap, 'id' | 'created_at' | 'updated_at'>
export type FinancialTypeMapUpdate = Partial<
  Pick<FinancialTypeMap, 'clean_financial_type' | 'acronyms' | 'is_active'>
>

// ─────────────────────────────────────────────────────────────
// heading_map
// ─────────────────────────────────────────────────────────────

export interface HeadingMap {
  id: string
  item_code: string
  data_type: string
  friendly_name: string
  category: string | null
  tier: number | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export type HeadingMapInsert = Omit<HeadingMap, 'id' | 'created_at' | 'updated_at'>
export type HeadingMapUpdate = Partial<
  Pick<HeadingMap, 'data_type' | 'friendly_name' | 'category' | 'tier' | 'is_active'>
>

// ─────────────────────────────────────────────────────────────
// heading_aliases
// ─────────────────────────────────────────────────────────────

export interface HeadingAlias {
  id: string
  heading_map_id: string
  alias: string
  alias_type: AliasType
  created_at: string
}

export type HeadingAliasInsert = Omit<HeadingAlias, 'id' | 'created_at'>

// ─────────────────────────────────────────────────────────────
// discrepancies
// ─────────────────────────────────────────────────────────────

export interface Discrepancy {
  id: string
  project_id: string
  sheet_name: string
  report_month: number      // 1–12
  report_year: number
  item_code: string | null
  data_type: string | null
  old_value: number | null
  new_value: number | null
  old_upload_id: string
  new_upload_id: string
  detected_at: string
  review_status: ReviewStatus
  reviewed_by: string | null    // Clerk user ID
  reviewed_at: string | null
  reviewer_note: string | null
  created_at: string
  updated_at: string
}

export type DiscrepancyInsert = Omit<
  Discrepancy,
  | 'id'
  | 'detected_at'
  | 'review_status'
  | 'reviewed_by'
  | 'reviewed_at'
  | 'reviewer_note'
  | 'created_at'
  | 'updated_at'
>

export type DiscrepancyUpdate = Partial<
  Pick<Discrepancy, 'review_status' | 'reviewed_by' | 'reviewed_at' | 'reviewer_note'>
>

// ─────────────────────────────────────────────────────────────
// query_logs
// ─────────────────────────────────────────────────────────────

export interface InterpretationOption {
  label: string
  params: {
    sheet_name?: string
    financial_type?: string
    data_type?: string
    item_code?: string
    month?: number
    year?: number
  }
}

export interface QueryLog {
  id: string
  project_id: string | null
  user_id: string               // Clerk user ID
  raw_query: string

  // Resolved parameters
  resolved_sheet_name: string | null
  resolved_financial_type: string | null
  resolved_data_type: string | null
  resolved_item_code: string | null
  resolved_month: number | null
  resolved_year: number | null
  resolved_shortcut: string | null

  // Ambiguity handling
  interpretation_options: InterpretationOption[] | null
  selected_option_index: number | null
  was_ambiguous: boolean

  // Response metadata
  mode: QueryMode
  response_type: ResponseType | null
  execution_ms: number | null

  created_at: string
}

export type QueryLogInsert = Omit<QueryLog, 'id' | 'created_at'>

// ─────────────────────────────────────────────────────────────
// admin_mapping_uploads
// ─────────────────────────────────────────────────────────────

export interface AdminMappingUpload {
  id: string
  mapping_type: MappingType
  storage_path: string          // Supabase Storage path
  original_filename: string
  uploaded_by: string           // Clerk user ID
  upload_timestamp: string
  validation_status: ValidationStatus
  row_count: number | null
  error_message: string | null
  is_applied: boolean
  applied_at: string | null
  created_at: string
}

export type AdminMappingUploadInsert = Omit<
  AdminMappingUpload,
  | 'id'
  | 'upload_timestamp'
  | 'validation_status'
  | 'row_count'
  | 'error_message'
  | 'is_applied'
  | 'applied_at'
  | 'created_at'
>

export type AdminMappingUploadUpdate = Partial<
  Pick<
    AdminMappingUpload,
    'validation_status' | 'row_count' | 'error_message' | 'is_applied' | 'applied_at'
  >
>

// ─────────────────────────────────────────────────────────────
// admin_notes
// ─────────────────────────────────────────────────────────────

export interface AdminNote {
  id: string
  project_id: string
  entity_type: 'query_log' | 'mapping_upload'
  entity_id: string
  note: string
  created_by: string
  created_at: string
  updated_at: string
}

export type AdminNoteInsert = Omit<AdminNote, 'id' | 'created_at' | 'updated_at'>
export type AdminNoteUpsert = Pick<AdminNote, 'entity_type' | 'entity_id' | 'note' | 'created_by' | 'project_id'>

// ─────────────────────────────────────────────────────────────
// Supabase Database type map (for use with createClient<Database>)
// ─────────────────────────────────────────────────────────────

// supabase-js v2.104+ GenericTable requires Relationships and GenericSchema
// requires Views. We declare both as empty since we don't use them.
type NoRelationships = { Relationships: [] }

export interface Database {
  public: {
    Tables: {
      projects: {
        Row: Project
        Insert: ProjectInsert
        Update: ProjectUpdate
      } & NoRelationships
      project_members: {
        Row: ProjectMember
        Insert: ProjectMemberInsert
        Update: ProjectMemberUpdate
      } & NoRelationships
      report_uploads: {
        Row: ReportUpload
        Insert: ReportUploadInsert
        Update: ReportUploadUpdate
      } & NoRelationships
      report_sheet_metadata: {
        Row: ReportSheetMetadata
        Insert: ReportSheetMetadataInsert
        Update: Partial<ReportSheetMetadataInsert>
      } & NoRelationships
      normalized_financial_rows: {
        Row: NormalizedFinancialRow
        Insert: NormalizedFinancialRowInsert
        Update: Partial<NormalizedFinancialRowInsert>
      } & NoRelationships
      financial_type_map: {
        Row: FinancialTypeMap
        Insert: FinancialTypeMapInsert
        Update: FinancialTypeMapUpdate
      } & NoRelationships
      heading_map: {
        Row: HeadingMap
        Insert: HeadingMapInsert
        Update: HeadingMapUpdate
      } & NoRelationships
      heading_aliases: {
        Row: HeadingAlias
        Insert: HeadingAliasInsert
        Update: Partial<HeadingAliasInsert>
      } & NoRelationships
      discrepancies: {
        Row: Discrepancy
        Insert: DiscrepancyInsert
        Update: DiscrepancyUpdate
      } & NoRelationships
      query_logs: {
        Row: QueryLog
        Insert: QueryLogInsert
        Update: Partial<QueryLogInsert>
      } & NoRelationships
      admin_mapping_uploads: {
        Row: AdminMappingUpload
        Insert: AdminMappingUploadInsert
        Update: AdminMappingUploadUpdate
      } & NoRelationships
      admin_notes: {
        Row: AdminNote
        Insert: AdminNoteInsert
        Update: Partial<AdminNoteUpsert>
      } & NoRelationships
    }
    Views: Record<string, never>
    Functions: {
      is_project_member: {
        Args: { p_project_id: string }
        Returns: boolean
      }
      is_project_admin: {
        Args: { p_project_id: string }
        Returns: boolean
      }
    }
  }
}
