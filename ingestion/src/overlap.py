"""
Source-of-truth activation and discrepancy detection.

resolve_overlap() is called at the end of _ingest() for valid/partial uploads.
It runs two sequential transactions:
  A: deactivate old rows + insert discrepancies + activate new rows (atomic)
  B: activate upload record
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .db import (
    activate_new_rows,
    activate_upload,
    deactivate_old_rows,
    find_active_overlapping_rows,
    insert_discrepancies,
)

log = logging.getLogger(__name__)


@dataclass
class OverlapResult:
    discrepancy_count: int
    deactivated_upload_ids: list[str] = field(default_factory=list)


def resolve_overlap(conn, upload_id: str, project_id: str) -> OverlapResult:
    """
    Detect overlap between the new upload and any previously active upload.

    Financial Status sheets are excluded (PRD §16.1) — their rows are still
    activated by activate_new_rows(), but no discrepancy records are created.
    """
    overlapping = find_active_overlapping_rows(conn, upload_id, project_id)

    if not overlapping:
        activate_new_rows(conn, upload_id)
        activate_upload(conn, upload_id, overlap_count=0)
        return OverlapResult(discrepancy_count=0)

    old_upload_ids: set[str] = set()
    discrepancy_records: list[dict] = []

    for row in overlapping:
        old_upload_ids.add(row["old_upload_id"])
        if row["old_value"] != row["new_value"]:
            discrepancy_records.append({
                "project_id": project_id,
                "sheet_name": row["sheet_name"],
                "report_month": row["report_month"],
                "report_year": row["report_year"],
                "item_code": row.get("item_code"),
                "financial_type": row.get("financial_type"),
                "data_type": row.get("data_type"),
                "old_value": row.get("old_value"),
                "new_value": row.get("new_value"),
                "old_upload_id": row["old_upload_id"],
                "new_upload_id": upload_id,
            })

    # Transaction A: deactivate old rows + insert discrepancies + activate new rows
    try:
        for old_upload_id in old_upload_ids:
            deactivate_old_rows(conn, old_upload_id, superseded_by_upload_id=upload_id)
        insert_discrepancies(conn, discrepancy_records)
        activate_new_rows(conn, upload_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    # Transaction B: activate upload record
    activate_upload(conn, upload_id, overlap_count=len(discrepancy_records))

    log.info(
        "Overlap resolved: upload=%s old_uploads=%d discrepancies=%d",
        upload_id,
        len(old_upload_ids),
        len(discrepancy_records),
    )

    return OverlapResult(
        discrepancy_count=len(discrepancy_records),
        deactivated_upload_ids=list(old_upload_ids),
    )
