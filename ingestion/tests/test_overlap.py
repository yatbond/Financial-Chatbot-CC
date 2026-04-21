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
