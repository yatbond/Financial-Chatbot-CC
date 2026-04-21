"""Database helpers using psycopg2. All functions accept an open connection."""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
import psycopg2.extras

from .config import DATABASE_URL

log = logging.getLogger(__name__)


def get_connection():
    return psycopg2.connect(DATABASE_URL)


# ── Upload record ─────────────────────────────────────────────────────────────

def get_upload(conn, upload_id: str) -> dict | None:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM report_uploads WHERE id = %s",
            (upload_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def update_upload_status(
    conn,
    upload_id: str,
    validation_status: str,
    ingestion_error: str | None = None,
    unmapped_heading_count: int = 0,
    unmapped_financial_type_count: int = 0,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE report_uploads
               SET validation_status = %s,
                   ingestion_error = %s,
                   unmapped_heading_count = %s,
                   unmapped_financial_type_count = %s,
                   updated_at = now()
             WHERE id = %s
            """,
            (
                validation_status,
                ingestion_error,
                unmapped_heading_count,
                unmapped_financial_type_count,
                upload_id,
            ),
        )
    conn.commit()


# ── Mapping tables ────────────────────────────────────────────────────────────

def load_financial_type_map(conn) -> dict[str, str]:
    """Returns {raw_financial_type: clean_financial_type}. Excludes *not used entries."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT raw_financial_type, clean_financial_type FROM financial_type_map WHERE is_active = true"
        )
        return {
            row[0]: row[1]
            for row in cur.fetchall()
            if not row[1].startswith("*")
        }


def load_heading_map(conn) -> dict[str, dict]:
    """Returns {item_code: {data_type, friendly_name, category, tier}}."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT item_code, data_type, friendly_name, category, tier FROM heading_map WHERE is_active = true"
        )
        return {row["item_code"]: dict(row) for row in cur.fetchall()}


# ── Sheet metadata ────────────────────────────────────────────────────────────

def upsert_sheet_metadata(conn, upload_id: str, sheet_name: str, data: dict) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO report_sheet_metadata
                (upload_id, sheet_name, row_count, mapped_row_count,
                 unmapped_row_count, parse_status, parse_error)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (upload_id, sheet_name)
            DO UPDATE SET
                row_count = EXCLUDED.row_count,
                mapped_row_count = EXCLUDED.mapped_row_count,
                unmapped_row_count = EXCLUDED.unmapped_row_count,
                parse_status = EXCLUDED.parse_status,
                parse_error = EXCLUDED.parse_error
            RETURNING id
            """,
            (
                upload_id,
                sheet_name,
                data.get("row_count"),
                data.get("mapped_row_count"),
                data.get("unmapped_row_count"),
                data.get("parse_status", "pending"),
                data.get("parse_error"),
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return row[0] if row else None


# ── Normalized rows ───────────────────────────────────────────────────────────

def insert_normalized_rows(conn, rows: list[dict]) -> int:
    if not rows:
        return 0
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO normalized_financial_rows (
                upload_id, project_id, sheet_name,
                report_month, report_year,
                raw_financial_type, financial_type,
                item_code, data_type, friendly_name, category, tier,
                value,
                source_row_number, source_cell_reference,
                is_active
            ) VALUES %s
            """,
            [
                (
                    r["upload_id"],
                    r["project_id"],
                    r["sheet_name"],
                    r["report_month"],
                    r["report_year"],
                    r.get("raw_financial_type"),
                    r.get("financial_type"),
                    r.get("item_code"),
                    r.get("data_type"),
                    r.get("friendly_name"),
                    r.get("category"),
                    r.get("tier"),
                    r.get("value"),
                    r.get("source_row_number"),
                    r.get("source_cell_reference"),
                    False,   # is_active — set to True by resolve_overlap()
                )
                for r in rows
            ],
            page_size=500,
        )
    conn.commit()
    return len(rows)


# ── Overlap detection ─────────────────────────────────────────────────────────

FINANCIAL_STATUS_SHEET = "Financial Status"


def find_active_overlapping_rows(conn, upload_id: str, project_id: str) -> list[dict]:
    """
    Returns rows where an existing active row (different upload) shares the
    overlap key with a newly inserted row for this upload.

    Excludes Financial Status sheet (PRD §16.1).

    Returns list of dicts with keys:
      old_upload_id, sheet_name, report_month, report_year,
      item_code, financial_type, data_type, old_value, new_value
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                old.upload_id        AS old_upload_id,
                old.sheet_name,
                old.report_month,
                old.report_year,
                old.item_code,
                old.financial_type,
                old.data_type,
                old.value            AS old_value,
                new_r.value          AS new_value
            FROM normalized_financial_rows AS old
            JOIN normalized_financial_rows AS new_r
                ON  old.project_id     = new_r.project_id
                AND old.sheet_name     = new_r.sheet_name
                AND old.report_month   = new_r.report_month
                AND old.report_year    = new_r.report_year
                AND old.item_code      IS NOT DISTINCT FROM new_r.item_code
                AND old.financial_type IS NOT DISTINCT FROM new_r.financial_type
            WHERE old.is_active = TRUE
              AND old.upload_id  != %s
              AND new_r.upload_id = %s
              AND new_r.project_id = %s
              AND old.sheet_name  != %s
              AND new_r.sheet_name != %s
            """,
            (upload_id, upload_id, project_id,
             FINANCIAL_STATUS_SHEET, FINANCIAL_STATUS_SHEET),
        )
        return [dict(row) for row in cur.fetchall()]


def deactivate_old_rows(conn, old_upload_id: str, superseded_by_upload_id: str) -> int:
    """
    Sets is_active=False and superseded_by_upload_id on all rows for old_upload_id.
    Does NOT commit — caller manages the transaction.
    Returns the number of rows deactivated.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE normalized_financial_rows
               SET is_active = FALSE,
                   superseded_by_upload_id = %s
             WHERE upload_id = %s
               AND is_active = TRUE
            """,
            (superseded_by_upload_id, old_upload_id),
        )
        return cur.rowcount


def activate_new_rows(conn, upload_id: str) -> int:
    """
    Sets is_active=True on all rows for upload_id.
    Does NOT commit — caller manages the transaction.
    Returns the number of rows activated.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE normalized_financial_rows
               SET is_active = TRUE
             WHERE upload_id = %s
               AND is_active = FALSE
            """,
            (upload_id,),
        )
        return cur.rowcount


def insert_discrepancies(conn, records: list[dict]) -> int:
    """
    Bulk-inserts discrepancy records.
    Does NOT commit — caller manages the transaction.
    Returns number of records inserted.
    """
    if not records:
        return 0
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO discrepancies (
                project_id, sheet_name, report_month, report_year,
                item_code, financial_type, data_type,
                old_value, new_value,
                old_upload_id, new_upload_id
            ) VALUES %s
            """,
            [
                (
                    r["project_id"],
                    r["sheet_name"],
                    r["report_month"],
                    r["report_year"],
                    r.get("item_code"),
                    r.get("financial_type"),
                    r.get("data_type"),
                    r.get("old_value"),
                    r.get("new_value"),
                    r["old_upload_id"],
                    r["new_upload_id"],
                )
                for r in records
            ],
            page_size=500,
        )
    return len(records)


def activate_upload(conn, upload_id: str, overlap_count: int) -> None:
    """
    Marks the upload as the active source of truth for its project+period.
    Deactivates any previously active upload for the same (project_id, report_month, report_year).
    Sets overlap_count to the number of discrepancy records created.
    Commits (transaction B).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE report_uploads
               SET is_active = FALSE, updated_at = now()
             WHERE project_id  = (SELECT project_id  FROM report_uploads WHERE id = %s)
               AND report_month = (SELECT report_month FROM report_uploads WHERE id = %s)
               AND report_year  = (SELECT report_year  FROM report_uploads WHERE id = %s)
               AND is_active = TRUE
               AND id != %s
            """,
            (upload_id, upload_id, upload_id, upload_id),
        )
        cur.execute(
            """
            UPDATE report_uploads
               SET is_active = TRUE, overlap_count = %s, updated_at = now()
             WHERE id = %s
            """,
            (overlap_count, upload_id),
        )
    conn.commit()
