# Ingestion Pipeline

> Stub — to be filled in during Phase 5 (Excel Parsing).

## Planned Flow

1. User uploads Excel report via web UI
2. Next.js stores file in Supabase Storage, creates `report_uploads` record
3. Next.js enqueues BullMQ job with `upload_id`
4. Python worker picks up job:
   - Parse workbook (openpyxl for .xlsx, xlrd for legacy .xls)
   - Identify sheets, extract report month/year
   - Normalize financial types via `financial_type_map`
   - Normalize headings via `heading_map`
   - Store mapped rows in `normalized_financial_rows`
   - Flag unmapped items for admin review
   - Detect overlapping historical values; create `discrepancies` records
   - Mark upload as active; prior uploads for same project/period superseded
5. Ingestion status dashboard updated in real time
