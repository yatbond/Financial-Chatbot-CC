"""
Bulk import script — ingests Excel financial reports into Supabase.

Expected filename format:
    {PROJECT_CODE} {PROJECT_NAME} Financial Report {YYYY-MM}.xlsx
    e.g. "1016 1WSD19 Financial Report 2026-02.xlsx"
         "969 Hiu Ming Street Financial Report 2026-02.xlsx"

Usage:
    uv run python bulk_import.py

Folders (edit below or pass as arguments):
    --unprocessed   Source folder  (default: /mnt/g/My Drive/Ai Chatbot Knowledge Base/Unprocessed)
    --processed     Dest folder    (default: /mnt/g/My Drive/Ai Chatbot Knowledge Base/Processed)

After a successful ingest the file is moved to the Processed folder.
Files that fail are left in Unprocessed with an error printed.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import uuid
from pathlib import Path

import httpx
import psycopg2.extras

from src.config import DATABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
from src.db import get_connection
from src.ingestion import run_ingestion

# ── Default folders (Windows Google Drive via WSL2 mount) ─────────────────────
DEFAULT_UNPROCESSED = "/mnt/g/My Drive/Ai Chatbot Knowledge Base/Unprocessed"
DEFAULT_PROCESSED   = "/mnt/g/My Drive/Ai Chatbot Knowledge Base/Processed"

BUCKET = "reports"

# Filename pattern:  {CODE} {NAME} Financial Report {YYYY-MM}.ext
_FILENAME_RE = re.compile(
    r'^(?P<code>\S+)\s+(?P<name>.+?)\s+Financial Report\s+(?P<year>20\d\d)-(?P<month>0[1-9]|1[0-2])',
    re.IGNORECASE,
)


def parse_filename(filename: str) -> dict | None:
    """
    Returns {code, name, year, month} or None if filename doesn't match.
    """
    m = _FILENAME_RE.match(Path(filename).stem)
    if not m:
        return None
    return {
        "code":  m.group("code").strip(),
        "name":  m.group("name").strip(),
        "year":  int(m.group("year")),
        "month": int(m.group("month")),
    }


def lookup_or_create_project(conn, code: str, name: str) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM projects WHERE project_code = %s AND project_name = %s LIMIT 1",
            (code, name),
        )
        row = cur.fetchone()
        if row:
            return str(row[0])

        # Also try by code alone (in case name differs slightly)
        cur.execute(
            "SELECT id, project_name FROM projects WHERE project_code = %s LIMIT 1",
            (code,),
        )
        row = cur.fetchone()
        if row:
            print(f"    Note: matched project by code '{code}' (DB name: '{row[1]}')")
            return str(row[0])

    # Create new project
    new_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO projects (id, project_code, project_name) VALUES (%s, %s, %s)",
            (new_id, code, name),
        )
    conn.commit()
    print(f"    Created new project: {code} — {name} ({new_id})")
    return new_id


def upload_to_storage(local_path: Path, storage_path: str) -> None:
    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{storage_path}"
    with open(local_path, "rb") as f:
        data = f.read()
    resp = httpx.put(
        url,
        content=data,
        headers={
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Content-Type": "application/octet-stream",
        },
        timeout=60,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Storage upload failed ({resp.status_code}): {resp.text}")


def create_upload_record(conn, project_id, storage_path, filename, month, year) -> str:
    upload_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO report_uploads
                (id, project_id, report_month, report_year,
                 storage_path, original_filename, uploaded_by, validation_status)
            VALUES (%s, %s, %s, %s, %s, %s, 'bulk-import', 'pending')
            """,
            (upload_id, project_id, month, year, storage_path, filename),
        )
    conn.commit()
    return upload_id


def process_file(conn, file: Path, unprocessed_dir: Path, processed_dir: Path) -> dict:
    print(f"\n  {'─' * 56}")
    print(f"  File : {file.name}")

    parsed = parse_filename(file.name)
    if not parsed:
        msg = "Filename does not match expected pattern — skipped"
        print(f"  SKIP : {msg}")
        return {"file": file.name, "status": "skipped", "reason": msg}

    code, name, month, year = parsed["code"], parsed["name"], parsed["month"], parsed["year"]
    print(f"  Code : {code}   Name : {name}   Period : {month:02d}/{year}")

    try:
        project_id = lookup_or_create_project(conn, code, name)
    except Exception as e:
        print(f"  ERROR: project lookup/create failed: {e}")
        return {"file": file.name, "status": "error", "reason": str(e)}

    storage_path = f"{project_id}/{file.name}"
    print(f"  Upload → {storage_path}")
    try:
        upload_to_storage(file, storage_path)
    except Exception as e:
        print(f"  ERROR: storage upload failed: {e}")
        return {"file": file.name, "status": "error", "reason": str(e)}

    upload_id = create_upload_record(conn, project_id, storage_path, file.name, month, year)
    print(f"  Ingesting (upload_id={upload_id}) ...")

    try:
        run_ingestion(upload_id)
    except Exception as e:
        print(f"  ERROR: ingestion failed: {e}")
        return {"file": file.name, "status": "error", "reason": str(e)}

    # Read final status from DB
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT validation_status, unmapped_heading_count, unmapped_financial_type_count "
            "FROM report_uploads WHERE id = %s",
            (upload_id,),
        )
        row = dict(cur.fetchone())

    status = row["validation_status"]
    unmapped_h  = row["unmapped_heading_count"]
    unmapped_ft = row["unmapped_financial_type_count"]

    if status in ("valid", "partial"):
        # Mirror subfolder structure from Unprocessed into Processed
        relative = file.parent.relative_to(unprocessed_dir)
        dest_dir = processed_dir / relative
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / file.name
        if dest.exists():
            dest = dest_dir / f"{file.stem}__{upload_id[:8]}{file.suffix}"
        shutil.move(str(file), str(dest))
        print(f"  {'OK' if status == 'valid' else 'PARTIAL'} : moved to Processed/{relative or '.'}")
        if unmapped_h or unmapped_ft:
            print(f"    Unmapped headings={unmapped_h}  financial types={unmapped_ft}")
        return {"file": file.name, "status": status, "project": f"{code} — {name}", "period": f"{month:02d}/{year}"}
    else:
        print(f"  FAIL : status={status} — file left in Unprocessed")
        return {"file": file.name, "status": status, "project": f"{code} — {name}", "period": f"{month:02d}/{year}"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk import Excel financial reports")
    parser.add_argument("--unprocessed", default=DEFAULT_UNPROCESSED, help="Source folder")
    parser.add_argument("--processed",   default=DEFAULT_PROCESSED,   help="Destination folder")
    args = parser.parse_args()

    unprocessed_dir = Path(args.unprocessed)
    processed_dir   = Path(args.processed)

    if not unprocessed_dir.is_dir():
        print(f"Error: Unprocessed folder not found:\n  {unprocessed_dir}")
        print("\nIf using Windows path, the WSL2 equivalent is:")
        print("  G:\\... → /mnt/g/...")
        sys.exit(1)

    processed_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(f for f in unprocessed_dir.rglob("*") if f.suffix.lower() in (".xlsx", ".xls"))
    if not files:
        print(f"No Excel files found in:\n  {unprocessed_dir}")
        sys.exit(0)

    print(f"\nFound {len(files)} file(s) (including subfolders)")
    print(f"  Unprocessed : {unprocessed_dir}")
    print(f"  Processed   : {processed_dir}")

    conn = get_connection()
    results = []

    for file in files:
        result = process_file(conn, file, unprocessed_dir, processed_dir)
        results.append(result)

    conn.close()

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'═' * 60}")
    print("  SUMMARY")
    print(f"{'═' * 60}")
    counts = {"valid": 0, "partial": 0, "error": 0, "skipped": 0}
    for r in results:
        status = r["status"]
        counts[status] = counts.get(status, 0) + 1
        icon = {"valid": "✓", "partial": "~", "error": "✗", "skipped": "-"}.get(status, "?")
        project = r.get("project", "")
        period  = r.get("period", "")
        reason  = r.get("reason", "")
        print(f"  {icon}  [{status:8s}]  {r['file']}")
        if project:
            print(f"            {project}  {period}")
        if reason:
            print(f"            {reason}")
    print()
    print(f"  Total: {len(results)}  |  valid={counts['valid']}  partial={counts['partial']}  error={counts['error']}  skipped={counts['skipped']}")
    print()


if __name__ == "__main__":
    main()
