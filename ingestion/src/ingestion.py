"""
Ingestion orchestrator.

Steps:
  1. Fetch upload record and project_id from DB
  2. Download Excel file from Supabase Storage
  3. Parse workbook into ExtractedRows
  4. Load mapping tables
  5. Normalise rows
  6. Write sheet metadata + normalized rows to DB
  7. Update upload status
"""

from __future__ import annotations

import logging
import os

from .db import (
    get_connection,
    get_upload,
    insert_normalized_rows,
    load_financial_type_map,
    load_heading_map,
    update_upload_status,
    upsert_sheet_metadata,
)
from .normalizer import normalize_rows
from .overlap import resolve_overlap
from .parser import WorkbookParseResult, parse_workbook
from .storage import download_file

log = logging.getLogger(__name__)


def run_ingestion(upload_id: str) -> None:
    conn = get_connection()
    try:
        _ingest(conn, upload_id)
    except Exception as exc:
        log.exception("Fatal error ingesting upload %s", upload_id)
        try:
            update_upload_status(conn, upload_id, "invalid", ingestion_error=str(exc))
        except Exception:
            log.exception("Could not update upload status after fatal error")
    finally:
        conn.close()


def _ingest(conn, upload_id: str) -> None:
    upload = get_upload(conn, upload_id)
    if not upload:
        raise ValueError(f"Upload {upload_id} not found")

    project_id: str = upload["project_id"]
    storage_path: str = upload["storage_path"]

    log.info("Starting ingestion: upload=%s project=%s path=%s", upload_id, project_id, storage_path)

    tmp_path = download_file(storage_path)
    try:
        wb_result: WorkbookParseResult = parse_workbook(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    financial_type_map = load_financial_type_map(conn)
    heading_map = load_heading_map(conn)

    total_unmapped_ft: set[str] = set()
    total_unmapped_ic: set[str] = set()
    total_rows = 0

    for sheet in wb_result.sheets:
        if sheet.skipped:
            upsert_sheet_metadata(conn, upload_id, sheet.original_name, {
                "row_count": 0,
                "mapped_row_count": 0,
                "unmapped_row_count": 0,
                "parse_status": "skipped",
                "parse_error": sheet.skipped_reason,
            })
            continue

        if sheet.error:
            upsert_sheet_metadata(conn, upload_id, sheet.original_name, {
                "row_count": 0,
                "mapped_row_count": 0,
                "unmapped_row_count": 0,
                "parse_status": "error",
                "parse_error": sheet.error,
            })
            continue

        norm = normalize_rows(
            sheet.rows,
            upload_id=upload_id,
            project_id=project_id,
            financial_type_map=financial_type_map,
            heading_map=heading_map,
        )

        mapped = sum(
            1 for r in norm.rows
            if r["financial_type"] is not None and r["data_type"] is not None
        )
        unmapped = len(norm.rows) - mapped

        upsert_sheet_metadata(conn, upload_id, sheet.original_name, {
            "row_count": len(norm.rows),
            "mapped_row_count": mapped,
            "unmapped_row_count": unmapped,
            "parse_status": "ok",
        })

        insert_normalized_rows(conn, norm.rows)

        total_unmapped_ft |= norm.unmapped_financial_types
        total_unmapped_ic |= norm.unmapped_item_codes
        total_rows += len(norm.rows)

    all_mapped = not total_unmapped_ft and not total_unmapped_ic
    validation_status = "valid" if all_mapped else "partial"

    update_upload_status(
        conn,
        upload_id,
        validation_status=validation_status,
        unmapped_financial_type_count=len(total_unmapped_ft),
        unmapped_heading_count=len(total_unmapped_ic),
    )

    try:
        overlap_result = resolve_overlap(conn, upload_id, project_id)
        log.info(
            "Overlap resolved: upload=%s discrepancies=%d deactivated=%s",
            upload_id,
            overlap_result.discrepancy_count,
            overlap_result.deactivated_upload_ids,
        )
    except Exception as exc:
        log.exception("Overlap resolution failed for upload %s", upload_id)
        update_upload_status(conn, upload_id, "invalid", ingestion_error=str(exc))
        return

    log.info(
        "Ingestion complete: upload=%s rows=%d status=%s unmapped_ft=%d unmapped_ic=%d discrepancies=%d",
        upload_id, total_rows, validation_status,
        len(total_unmapped_ft), len(total_unmapped_ic),
        overlap_result.discrepancy_count,
    )
