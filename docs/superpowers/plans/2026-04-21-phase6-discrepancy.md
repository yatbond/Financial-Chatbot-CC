# Phase 6 — Source-of-Truth Activation & Discrepancy Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After Phase 5 inserts normalized rows, detect overlap with prior active uploads, deactivate old rows, create discrepancy records where values differ, and activate the new upload as source of truth.

**Architecture:** A new `overlap.py` module calls five new DB helpers from `db.py`. `insert_normalized_rows` is changed to insert with `is_active=False`; rows are only activated once overlap detection completes atomically. `resolve_overlap()` runs two sequential transactions: transaction A (deactivate old rows + insert discrepancies + activate new rows) and transaction B (activate upload record). Financial Status sheets are excluded from overlap detection.

**Tech Stack:** Python 3.12, psycopg2, pytest, unittest.mock — no new dependencies.

---

## File Map

| File | Change |
|------|--------|
| `web/supabase/migrations/20260421000002_discrepancies_financial_type.sql` | **Create** — adds `financial_type TEXT` column to `discrepancies` table |
| `ingestion/src/db.py` | **Modify** — change `insert_normalized_rows` default to `is_active=False`; add 5 new helpers |
| `ingestion/src/overlap.py` | **Create** — `OverlapResult` dataclass + `resolve_overlap()` |
| `ingestion/src/ingestion.py` | **Modify** — call `resolve_overlap()` at end of `_ingest()` |
| `ingestion/tests/test_overlap.py` | **Create** — 7 unit tests for `resolve_overlap()` using mocked DB helpers |

---

## Task 1: DB Migration — Add `financial_type` to `discrepancies`

**Files:**
- Create: `web/supabase/migrations/20260421000002_discrepancies_financial_type.sql`

- [ ] **Step 1.1: Create the migration file**

```sql
-- Migration: add financial_type column to discrepancies
-- Needed by Phase 6 overlap detection (PRD §16.5 "financial concept" field).
-- The overlap key in normalized_financial_rows includes financial_type,
-- so discrepancy records must capture it for admin review in Phase 11.

ALTER TABLE discrepancies
  ADD COLUMN financial_type TEXT;

-- Rebuild overlap key index to include financial_type
DROP INDEX IF EXISTS idx_disc_overlap_key;
CREATE INDEX idx_disc_overlap_key
  ON discrepancies (project_id, sheet_name, report_month, report_year, item_code, financial_type);
```

- [ ] **Step 1.2: Verify the file is syntactically valid (dry run)**

```bash
cd "/home/yatbond/projects/financial chatbot/web"
# Check the file exists and looks correct
cat supabase/migrations/20260421000002_discrepancies_financial_type.sql
```

Expected: file prints cleanly with the ALTER TABLE and DROP/CREATE INDEX statements.

- [ ] **Step 1.3: Commit**

```bash
cd "/home/yatbond/projects/financial chatbot"
git add web/supabase/migrations/20260421000002_discrepancies_financial_type.sql
git commit -m "feat(phase-6): migration — add financial_type to discrepancies"
```

---

## Task 2: Change `insert_normalized_rows` Default to `is_active=False`

**Files:**
- Modify: `ingestion/src/db.py` (line ~150, the `True` in the VALUES tuple)

Rows must start inactive so that `resolve_overlap()` can activate them atomically with old-row deactivation. Without this change, a failed overlap transaction would leave both old and new rows active.

- [ ] **Step 2.1: Edit `insert_normalized_rows` in `ingestion/src/db.py`**

Find the VALUES tuple inside `insert_normalized_rows`. It ends with `True,` for `is_active`. Change it to `False,`:

```python
                    r.get("source_cell_reference"),
                    False,   # is_active — set to True by resolve_overlap()
```

The full tuple after the change (for reference):
```python
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
```

- [ ] **Step 2.2: Verify existing tests still pass**

```bash
cd "/home/yatbond/projects/financial chatbot/ingestion"
uv run pytest tests/test_parser.py -v
```

Expected: all existing tests PASS (they test the parser, not `db.py`).

- [ ] **Step 2.3: Commit**

```bash
cd "/home/yatbond/projects/financial chatbot"
git add ingestion/src/db.py
git commit -m "feat(phase-6): insert normalized rows as inactive pending overlap resolution"
```

---

## Task 3: Add DB Helper — `find_active_overlapping_rows`

**Files:**
- Modify: `ingestion/src/db.py`

This is the read query that finds (old active row, new row) pairs sharing the overlap key. It's the core detection logic.

- [ ] **Step 3.1: Append `find_active_overlapping_rows` to `ingestion/src/db.py`**

Add at the bottom of the file, after `insert_normalized_rows`:

```python
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
```

- [ ] **Step 3.2: Run existing tests to confirm no regression**

```bash
cd "/home/yatbond/projects/financial chatbot/ingestion"
uv run pytest tests/ -v
```

Expected: all tests PASS.

---

## Task 4: Add Remaining DB Helpers

**Files:**
- Modify: `ingestion/src/db.py`

Four helpers: deactivate old rows, activate new rows, bulk-insert discrepancies, activate upload record.

- [ ] **Step 4.1: Append `deactivate_old_rows` to `ingestion/src/db.py`**

```python
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
```

- [ ] **Step 4.2: Append `activate_new_rows` to `ingestion/src/db.py`**

```python
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
```

- [ ] **Step 4.3: Append `insert_discrepancies` to `ingestion/src/db.py`**

```python
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
```

- [ ] **Step 4.4: Append `activate_upload` to `ingestion/src/db.py`**

```python
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
```

- [ ] **Step 4.5: Run tests**

```bash
cd "/home/yatbond/projects/financial chatbot/ingestion"
uv run pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 4.6: Commit**

```bash
cd "/home/yatbond/projects/financial chatbot"
git add ingestion/src/db.py
git commit -m "feat(phase-6): add overlap detection and activation DB helpers"
```

---

## Task 5: Write Failing Tests for `resolve_overlap`

**Files:**
- Create: `ingestion/tests/test_overlap.py`

Tests use `unittest.mock.patch` to mock the five DB helpers imported by `overlap.py`. This lets us test the orchestration logic without a real database.

- [ ] **Step 5.1: Create `ingestion/tests/test_overlap.py`**

```python
"""Unit tests for overlap.py — DB helpers are mocked."""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

# These imports will fail until overlap.py is created (Task 6) — that's expected.
from src.overlap import OverlapResult, resolve_overlap

PROJECT_ID = "proj-abc"
UPLOAD_ID = "upload-new"
OLD_UPLOAD_ID = "upload-old"

MODULE = "src.overlap"


def _conn():
    """Return a mock psycopg2 connection."""
    conn = MagicMock()
    return conn


# ── 1. No prior active upload ─────────────────────────────────────────────────

class TestNoOverlap:
    def test_no_prior_active_upload(self):
        """When no active rows overlap, new rows are activated and upload is activated."""
        conn = _conn()
        with (
            patch(f"{MODULE}.find_active_overlapping_rows", return_value=[]) as mock_find,
            patch(f"{MODULE}.activate_new_rows") as mock_activate_rows,
            patch(f"{MODULE}.activate_upload") as mock_activate_upload,
            patch(f"{MODULE}.deactivate_old_rows") as mock_deactivate,
            patch(f"{MODULE}.insert_discrepancies") as mock_insert_disc,
        ):
            result = resolve_overlap(conn, UPLOAD_ID, PROJECT_ID)

        assert isinstance(result, OverlapResult)
        assert result.discrepancy_count == 0
        assert result.deactivated_upload_ids == []
        mock_find.assert_called_once_with(conn, UPLOAD_ID, PROJECT_ID)
        mock_activate_rows.assert_called_once_with(conn, UPLOAD_ID)
        mock_activate_upload.assert_called_once_with(conn, UPLOAD_ID, overlap_count=0)
        mock_deactivate.assert_not_called()
        mock_insert_disc.assert_not_called()


# ── 2. Prior upload — all values match ────────────────────────────────────────

class TestOverlapNoDiscrepancies:
    def test_all_values_match_no_discrepancies(self):
        """When values are identical, old rows are deactivated but no discrepancies are created."""
        conn = _conn()
        overlapping = [
            {
                "old_upload_id": OLD_UPLOAD_ID,
                "sheet_name": "Projection",
                "report_month": 1,
                "report_year": 2026,
                "item_code": "1",
                "financial_type": "Committed Cost",
                "data_type": "Contract Sum",
                "old_value": 100.0,
                "new_value": 100.0,
            }
        ]
        with (
            patch(f"{MODULE}.find_active_overlapping_rows", return_value=overlapping),
            patch(f"{MODULE}.deactivate_old_rows") as mock_deactivate,
            patch(f"{MODULE}.insert_discrepancies") as mock_insert_disc,
            patch(f"{MODULE}.activate_new_rows") as mock_activate_rows,
            patch(f"{MODULE}.activate_upload") as mock_activate_upload,
        ):
            result = resolve_overlap(conn, UPLOAD_ID, PROJECT_ID)

        assert result.discrepancy_count == 0
        assert OLD_UPLOAD_ID in result.deactivated_upload_ids
        mock_deactivate.assert_called_once_with(conn, OLD_UPLOAD_ID, superseded_by_upload_id=UPLOAD_ID)
        mock_insert_disc.assert_called_once_with(conn, [])
        mock_activate_rows.assert_called_once_with(conn, UPLOAD_ID)
        mock_activate_upload.assert_called_once_with(conn, UPLOAD_ID, overlap_count=0)
        conn.commit.assert_called_once()


# ── 3. Prior upload — some values differ ──────────────────────────────────────

class TestOverlapWithDiscrepancies:
    def test_differing_values_create_discrepancy_records(self):
        """When values differ, discrepancy records are created and overlap_count is set."""
        conn = _conn()
        overlapping = [
            {
                "old_upload_id": OLD_UPLOAD_ID,
                "sheet_name": "Projection",
                "report_month": 1,
                "report_year": 2026,
                "item_code": "1",
                "financial_type": "Committed Cost",
                "data_type": "Contract Sum",
                "old_value": 100.0,
                "new_value": 150.0,  # differs
            },
            {
                "old_upload_id": OLD_UPLOAD_ID,
                "sheet_name": "Projection",
                "report_month": 1,
                "report_year": 2026,
                "item_code": "2",
                "financial_type": "Committed Cost",
                "data_type": "Variations",
                "old_value": 50.0,
                "new_value": 50.0,  # same
            },
        ]
        with (
            patch(f"{MODULE}.find_active_overlapping_rows", return_value=overlapping),
            patch(f"{MODULE}.deactivate_old_rows"),
            patch(f"{MODULE}.insert_discrepancies") as mock_insert_disc,
            patch(f"{MODULE}.activate_new_rows"),
            patch(f"{MODULE}.activate_upload") as mock_activate_upload,
        ):
            result = resolve_overlap(conn, UPLOAD_ID, PROJECT_ID)

        assert result.discrepancy_count == 1
        discrepancy_records = mock_insert_disc.call_args[0][1]
        assert len(discrepancy_records) == 1
        rec = discrepancy_records[0]
        assert rec["old_value"] == 100.0
        assert rec["new_value"] == 150.0
        assert rec["item_code"] == "1"
        assert rec["financial_type"] == "Committed Cost"
        assert rec["old_upload_id"] == OLD_UPLOAD_ID
        assert rec["new_upload_id"] == UPLOAD_ID
        assert rec["project_id"] == PROJECT_ID
        mock_activate_upload.assert_called_once_with(conn, UPLOAD_ID, overlap_count=1)
        conn.commit.assert_called_once()


# ── 4. Financial Status only — no overlap logic ───────────────────────────────

class TestFinancialStatusOnly:
    def test_financial_status_upload_skips_overlap(self):
        """find_active_overlapping_rows returns empty for FS-only uploads; upload still activated."""
        conn = _conn()
        # find_active_overlapping_rows always excludes Financial Status at the SQL level,
        # so it will return [] even if the workbook only has a Financial Status sheet.
        with (
            patch(f"{MODULE}.find_active_overlapping_rows", return_value=[]) as mock_find,
            patch(f"{MODULE}.activate_new_rows") as mock_activate_rows,
            patch(f"{MODULE}.activate_upload") as mock_activate_upload,
            patch(f"{MODULE}.deactivate_old_rows") as mock_deactivate,
            patch(f"{MODULE}.insert_discrepancies") as mock_insert_disc,
        ):
            result = resolve_overlap(conn, UPLOAD_ID, PROJECT_ID)

        assert result.discrepancy_count == 0
        mock_activate_rows.assert_called_once_with(conn, UPLOAD_ID)
        mock_activate_upload.assert_called_once_with(conn, UPLOAD_ID, overlap_count=0)
        mock_deactivate.assert_not_called()
        mock_insert_disc.assert_not_called()


# ── 5. Mixed sheets — only monthly overlap detected ───────────────────────────

class TestMixedSheets:
    def test_only_monthly_rows_returned_by_find(self):
        """Financial Status rows are excluded by the SQL query; only monthly overlap is returned."""
        conn = _conn()
        # Simulate: find returns one monthly overlap (FS was excluded by SQL)
        overlapping = [
            {
                "old_upload_id": OLD_UPLOAD_ID,
                "sheet_name": "Cash Flow",
                "report_month": 2,
                "report_year": 2026,
                "item_code": "3",
                "financial_type": "Accrual",
                "data_type": "Subcontractors",
                "old_value": 200.0,
                "new_value": 210.0,
            }
        ]
        with (
            patch(f"{MODULE}.find_active_overlapping_rows", return_value=overlapping),
            patch(f"{MODULE}.deactivate_old_rows"),
            patch(f"{MODULE}.insert_discrepancies") as mock_insert_disc,
            patch(f"{MODULE}.activate_new_rows"),
            patch(f"{MODULE}.activate_upload") as mock_activate_upload,
        ):
            result = resolve_overlap(conn, UPLOAD_ID, PROJECT_ID)

        assert result.discrepancy_count == 1
        recs = mock_insert_disc.call_args[0][1]
        assert recs[0]["sheet_name"] == "Cash Flow"
        mock_activate_upload.assert_called_once_with(conn, UPLOAD_ID, overlap_count=1)


# ── 6. Transaction rollback on error ─────────────────────────────────────────

class TestTransactionRollback:
    def test_rollback_on_deactivate_error(self):
        """If deactivate_old_rows raises, conn.rollback() is called and exception propagates."""
        conn = _conn()
        overlapping = [
            {
                "old_upload_id": OLD_UPLOAD_ID,
                "sheet_name": "Projection",
                "report_month": 1,
                "report_year": 2026,
                "item_code": "1",
                "financial_type": "Committed Cost",
                "data_type": "Contract Sum",
                "old_value": 100.0,
                "new_value": 200.0,
            }
        ]
        with (
            patch(f"{MODULE}.find_active_overlapping_rows", return_value=overlapping),
            patch(f"{MODULE}.deactivate_old_rows", side_effect=RuntimeError("DB error")),
            patch(f"{MODULE}.insert_discrepancies"),
            patch(f"{MODULE}.activate_new_rows"),
            patch(f"{MODULE}.activate_upload") as mock_activate_upload,
        ):
            with pytest.raises(RuntimeError, match="DB error"):
                resolve_overlap(conn, UPLOAD_ID, PROJECT_ID)

        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()
        mock_activate_upload.assert_not_called()


# ── 7. Multiple old upload IDs deactivated ────────────────────────────────────

class TestMultipleOldUploads:
    def test_two_old_uploads_both_deactivated(self):
        """If overlap rows come from two different old uploads, both are deactivated."""
        conn = _conn()
        OLD_UPLOAD_ID_2 = "upload-old-2"
        overlapping = [
            {
                "old_upload_id": OLD_UPLOAD_ID,
                "sheet_name": "Projection",
                "report_month": 1,
                "report_year": 2026,
                "item_code": "1",
                "financial_type": "Committed Cost",
                "data_type": "Contract Sum",
                "old_value": 100.0,
                "new_value": 200.0,
            },
            {
                "old_upload_id": OLD_UPLOAD_ID_2,
                "sheet_name": "Accrual",
                "report_month": 1,
                "report_year": 2026,
                "item_code": "2",
                "financial_type": "Accrual",
                "data_type": "Subcontractors",
                "old_value": 50.0,
                "new_value": 60.0,
            },
        ]
        with (
            patch(f"{MODULE}.find_active_overlapping_rows", return_value=overlapping),
            patch(f"{MODULE}.deactivate_old_rows") as mock_deactivate,
            patch(f"{MODULE}.insert_discrepancies"),
            patch(f"{MODULE}.activate_new_rows"),
            patch(f"{MODULE}.activate_upload"),
        ):
            result = resolve_overlap(conn, UPLOAD_ID, PROJECT_ID)

        assert result.discrepancy_count == 2
        assert set(result.deactivated_upload_ids) == {OLD_UPLOAD_ID, OLD_UPLOAD_ID_2}
        deactivated_ids = {c.args[1] for c in mock_deactivate.call_args_list}
        assert deactivated_ids == {OLD_UPLOAD_ID, OLD_UPLOAD_ID_2}
```

- [ ] **Step 5.2: Run tests to confirm they all fail (overlap.py doesn't exist yet)**

```bash
cd "/home/yatbond/projects/financial chatbot/ingestion"
uv run pytest tests/test_overlap.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'src.overlap'` or similar import error. All 7 tests fail.

---

## Task 6: Create `overlap.py` — Make Tests Pass

**Files:**
- Create: `ingestion/src/overlap.py`

- [ ] **Step 6.1: Create `ingestion/src/overlap.py`**

```python
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
```

- [ ] **Step 6.2: Run the overlap tests — all must pass**

```bash
cd "/home/yatbond/projects/financial chatbot/ingestion"
uv run pytest tests/test_overlap.py -v
```

Expected output:
```
tests/test_overlap.py::TestNoOverlap::test_no_prior_active_upload PASSED
tests/test_overlap.py::TestOverlapNoDiscrepancies::test_all_values_match_no_discrepancies PASSED
tests/test_overlap.py::TestOverlapWithDiscrepancies::test_differing_values_create_discrepancy_records PASSED
tests/test_overlap.py::TestFinancialStatusOnly::test_financial_status_upload_skips_overlap PASSED
tests/test_overlap.py::TestMixedSheets::test_only_monthly_rows_returned_by_find PASSED
tests/test_overlap.py::TestTransactionRollback::test_rollback_on_deactivate_error PASSED
tests/test_overlap.py::TestMultipleOldUploads::test_two_old_uploads_both_deactivated PASSED

7 passed
```

If any test fails, read the error and fix `overlap.py`. Do NOT change the tests.

- [ ] **Step 6.3: Run full test suite**

```bash
cd "/home/yatbond/projects/financial chatbot/ingestion"
uv run pytest tests/ -v
```

Expected: all tests (including test_parser.py) PASS.

- [ ] **Step 6.4: Commit**

```bash
cd "/home/yatbond/projects/financial chatbot"
git add ingestion/src/overlap.py ingestion/tests/test_overlap.py
git commit -m "feat(phase-6): overlap module and unit tests — source-of-truth activation and discrepancy detection"
```

---

## Task 7: Wire `resolve_overlap` into `ingestion.py`

**Files:**
- Modify: `ingestion/src/ingestion.py`

- [ ] **Step 7.1: Add import at the top of `ingestion/src/ingestion.py`**

After the existing imports from `.db`, add:

```python
from .overlap import resolve_overlap
```

The full imports block should look like:

```python
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
```

- [ ] **Step 7.2: Call `resolve_overlap` at the end of `_ingest()`**

Find the end of `_ingest()`, after the `update_upload_status(...)` call. The current last call is:

```python
    log.info(
        "Ingestion complete: upload=%s rows=%d status=%s unmapped_ft=%d unmapped_ic=%d",
        upload_id, total_rows, validation_status,
        len(total_unmapped_ft), len(total_unmapped_ic),
    )
```

Add the `resolve_overlap` call between `update_upload_status` and the final `log.info`. The modified tail of `_ingest()` should be:

```python
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
```

- [ ] **Step 7.3: Run all tests**

```bash
cd "/home/yatbond/projects/financial chatbot/ingestion"
uv run pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 7.4: Commit**

```bash
cd "/home/yatbond/projects/financial chatbot"
git add ingestion/src/ingestion.py
git commit -m "feat(phase-6): wire resolve_overlap into ingestion pipeline"
```

---

## Task 8: Final Verification

- [ ] **Step 8.1: Run full test suite one more time**

```bash
cd "/home/yatbond/projects/financial chatbot/ingestion"
uv run pytest tests/ -v --tb=short
```

Expected: all tests PASS, no warnings about missing modules.

- [ ] **Step 8.2: Check all Phase 6 files are committed**

```bash
cd "/home/yatbond/projects/financial chatbot"
git log --oneline -6
git status
```

Expected:
- `git status` shows clean working tree
- Log shows 5 Phase 6 commits:
  1. migration
  2. `insert_normalized_rows` default change
  3. DB helpers
  4. overlap module + tests
  5. wire into ingestion

- [ ] **Step 8.3: Manual test steps (requires Supabase + ingestion service running)**

1. Apply the migration:
   ```bash
   cd web && npx supabase db push
   ```
2. Upload a report for Project A, Month Jan 2026. Check `report_uploads.is_active = true`, `normalized_financial_rows.is_active = true`, zero `discrepancies`.
3. Upload a second report for the same Project A, Month Jan 2026, with at least one changed value. Check:
   - Old upload: `is_active = false`
   - New upload: `is_active = true`, `overlap_count > 0`
   - `discrepancies` table has one row per changed value with correct `old_value`, `new_value`, `financial_type`
   - Old `normalized_financial_rows` rows: `is_active = false`, `superseded_by_upload_id` = new upload ID
4. Upload a report with only a Financial Status sheet. Check: no discrepancies, upload activates cleanly.
