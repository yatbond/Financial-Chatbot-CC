# Data Model

> Stub — to be filled in during Phase 1 (Database Schema).

## Core Tables (planned)

- `projects` — project code + name
- `project_members` — user access per project
- `report_uploads` — uploaded Excel files with validation status
- `report_sheet_metadata` — per-sheet metadata per upload
- `normalized_financial_rows` — extracted rows with row/cell trace
- `financial_type_map` — canonical mapping: raw financial type → clean name
- `heading_map` — canonical mapping: item code, friendly name, category, tier
- `heading_aliases` — alternate names for query resolution
- `discrepancies` — detected overlapping value conflicts
- `query_logs` — audit trail of all queries
- `admin_mapping_uploads` — history of mapping CSV uploads
