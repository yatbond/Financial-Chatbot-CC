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
