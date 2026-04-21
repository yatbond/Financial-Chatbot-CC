# Phase 6 — Source-of-Truth Activation & Discrepancy Engine

**Date:** 2026-04-21  
**Status:** Approved  
**PRD refs:** §16.1–16.5, §17.1 steps 8–10  
**Dev plan:** Phase 6

---

## Objective

After Phase 5 inserts normalized rows, Phase 6 adds the logic that:
- detects overlap between the new upload and any previously active upload for the same project/period/sheet
- deactivates old rows and creates discrepancy records where values differ
- activates the new upload as the source of truth

Financial Status sheets are excluded from overlap detection (PRD §16.1).

---

## Schema Change

**Migration:** `web/supabase/migrations/20260421000002_discrepancies_financial_type.sql`

Add `financial_type TEXT` to the `discrepancies` table. PRD §16.5 requires "financial concept" as a discrepancy field, and the overlap key in `normalized_financial_rows` already includes `financial_type`. The existing `idx_disc_overlap_key` index is dropped and recreated to include `financial_type`.

---

## Architecture

### New file: `ingestion/src/overlap.py`

Single public function: `resolve_overlap(conn, upload_id, project_id) -> OverlapResult`

Called at the end of `_ingest()`, after all sheets are inserted, only when `validation_status` is `valid` or `partial`. Never called for `invalid` uploads.

`OverlapResult` is a dataclass:
```python
@dataclass
class OverlapResult:
    discrepancy_count: int
    deactivated_upload_ids: list[str]
```

### Changes to `ingestion/src/db.py`

Four new helpers:

| Function | Purpose |
|----------|---------|
| `find_active_overlapping_rows(conn, upload_id, project_id)` | Returns active rows (from a different upload) that share `(project_id, sheet_name, report_month, report_year, item_code, financial_type)` with the new upload. Excludes `Financial Status` sheet. |
| `deactivate_old_rows(conn, old_upload_id, superseded_by_upload_id)` | Sets `is_active=False`, `superseded_by_upload_id` on all rows for `old_upload_id`. |
| `activate_new_rows(conn, upload_id)` | Sets `is_active=True` on all rows for `upload_id`. Called inside transaction A. |
| `insert_discrepancies(conn, records)` | Bulk-inserts into `discrepancies`. |
| `activate_upload(conn, upload_id, overlap_count)` | Sets new upload `is_active=True`, sets any previously active upload for same `(project_id, report_month, report_year)` to `is_active=False`, updates `overlap_count`. |

### Changes to `ingestion/src/db.py` (Phase 5 insert default)

`insert_normalized_rows` is changed to insert rows with `is_active=False`. Rows only become active once `resolve_overlap()` completes successfully. This prevents a corrupt dual-active state if transaction A fails after insert.

### Changes to `ingestion/src/ingestion.py`

- Import and call `resolve_overlap()` at the end of `_ingest()`, after `update_upload_status()`.
- `activate_upload()` sets `overlap_count` on the upload record — `update_upload_status()` is not changed.
- Wrap in try/except: if `resolve_overlap()` raises, set `validation_status='invalid'` with the error.

---

## Data Flow

```
_ingest()
  │
  ├─ [existing] parse → normalize → insert_normalized_rows(is_active=False) → update_upload_status(valid|partial)
  │
  └─ resolve_overlap(conn, upload_id, project_id)
       │
       ├─ 1. Load new upload's non-Financial-Status rows from normalized_financial_rows
       │      (all have is_active=False at this point)
       │
       ├─ 2. For each distinct (sheet_name, report_month, report_year):
       │      query is_active=True rows for same project+sheet+period (different upload)
       │      if none → skip period (no old rows to deactivate)
       │
       ├─ 3. Match old rows on (item_code, financial_type)
       │      value differs → queue discrepancy record
       │      all matched old rows → queued for deactivation
       │
       ├─ 4. [transaction A] deactivate_old_rows + insert_discrepancies + activate_new_rows (atomic)
       │      — sets old rows is_active=False, superseded_by_upload_id=new_upload_id
       │      — inserts discrepancy records
       │      — sets new rows is_active=True
       │
       └─ 5. [transaction B] activate_upload(new_upload_id, overlap_count)
                sets new upload is_active=True
                sets old upload is_active=False
                sets overlap_count = discrepancy_count
```

---

## Financial Status Handling

- Steps 1–4 are skipped entirely for any row where `sheet_name = 'Financial Status'`.
- Step 5 (`activate_upload`) still runs — the new upload becomes the active record for its period.
- No old Financial Status rows are deactivated; no discrepancies are created for them.
- Rationale: each report's Financial Status is a distinct snapshot of that report date (PRD §16.1).

---

## Error Handling

- `deactivate_old_rows`, `insert_discrepancies`, and `activate_new_rows` run in **one transaction (A)**. If any step fails, all roll back — no partial state. New rows remain `is_active=False`.
- `activate_upload` runs in a **separate transaction (B)** after A commits.
- If `resolve_overlap()` raises at any point, `_ingest()` catches it and sets `validation_status='invalid'` with the error string. The upload remains unactivated; its rows remain `is_active=False`. No dual-active state is possible.
- Re-ingesting: because rows are inserted with `is_active=False`, a second ingestion attempt would need to handle duplicate rows. This is a known limitation — Phase 6 does not add idempotent re-ingestion; that is deferred to a later phase.

---

## Testing

**New file:** `ingestion/tests/test_overlap.py`

Test cases:
1. **No prior active upload** → rows inserted, upload activated, `discrepancy_count=0`
2. **Prior upload, all values match** → old rows deactivated, upload activated, zero discrepancy records
3. **Prior upload, some values differ** → old rows deactivated, discrepancy records created, `overlap_count` matches count of differing rows
4. **Financial Status sheet only** → overlap logic skipped, upload activated, no discrepancies
5. **Mixed sheets (Financial Status + monthly)** → only monthly sheets checked for overlap
6. **Invalid upload** → `resolve_overlap()` not called
7. **resolve_overlap() raises** → `validation_status='invalid'`, upload not activated

Tests use mock connections consistent with the pattern in `tests/test_parser.py`.

---

## What Phase 6 Does NOT Do

- No discrepancy review UI (Phase 11)
- No chatbot exposure of discrepancies (Phase 10)
- No change to parsing scope from Phase 5
- No new upload trigger flow — Phase 5's fire-and-forget POST is unchanged
