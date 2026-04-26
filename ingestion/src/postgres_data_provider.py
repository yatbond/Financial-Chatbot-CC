"""PostgresDataProvider — DataProvider backed by normalized_financial_rows via psycopg2."""

from __future__ import annotations

import psycopg2.extras

from .shortcut_engine import DataProvider, FinancialRow


class PostgresDataProvider(DataProvider):
    """DataProvider that queries normalized_financial_rows via psycopg2."""

    def __init__(self, conn) -> None:
        self._conn = conn

    def fetch_rows(
        self,
        project_id: str,
        sheet_name: str,
        *,
        financial_type: str | None = None,
        item_code: str | None = None,
        data_type: str | None = None,
        report_month: int | None = None,
        report_year: int | None = None,
        item_code_prefix: str | None = None,
        is_active: bool = True,
    ) -> list[FinancialRow]:
        clauses = ["project_id = %s", "sheet_name = %s", "is_active = %s"]
        params: list = [project_id, sheet_name, is_active]

        if financial_type is not None:
            clauses.append("financial_type = %s")
            params.append(financial_type)
        if item_code is not None:
            clauses.append("item_code = %s")
            params.append(item_code)
        if data_type is not None:
            clauses.append("data_type = %s")
            params.append(data_type)
        if report_month is not None:
            clauses.append("report_month = %s")
            params.append(report_month)
        if report_year is not None:
            clauses.append("report_year = %s")
            params.append(report_year)
        if item_code_prefix is not None:
            clauses.append("(item_code = %s OR item_code LIKE %s)")
            params.extend([item_code_prefix, item_code_prefix + ".%"])

        sql = (
            "SELECT project_id, sheet_name, report_month, report_year, "
            "financial_type, item_code, data_type, friendly_name, category, tier, value "
            "FROM normalized_financial_rows WHERE " + " AND ".join(clauses)
        )
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [_to_row(dict(r)) for r in cur.fetchall()]

    def fetch_rows_for_periods(
        self,
        project_id: str,
        sheet_name: str,
        financial_type: str | None,
        item_code: str | None,
        periods: list[tuple[int, int]],
        is_active: bool = True,
    ) -> list[FinancialRow]:
        if not periods:
            return []
        period_clause = " OR ".join(["(report_month = %s AND report_year = %s)"] * len(periods))
        clauses = [
            "project_id = %s", "sheet_name = %s", "is_active = %s",
            f"({period_clause})",
        ]
        params: list = [project_id, sheet_name, is_active]
        for m, y in periods:
            params.extend([m, y])

        if financial_type is not None:
            clauses.append("financial_type = %s")
            params.append(financial_type)
        if item_code is not None:
            clauses.append("item_code = %s")
            params.append(item_code)

        sql = (
            "SELECT project_id, sheet_name, report_month, report_year, "
            "financial_type, item_code, data_type, friendly_name, category, tier, value "
            "FROM normalized_financial_rows WHERE " + " AND ".join(clauses)
        )
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [_to_row(dict(r)) for r in cur.fetchall()]

    def get_latest_period(
        self,
        project_id: str,
        sheet_name: str,
        financial_type: str | None = None,
    ) -> tuple[int, int] | None:
        sql = (
            "SELECT report_month, report_year FROM normalized_financial_rows "
            "WHERE project_id = %s AND sheet_name = %s AND is_active = TRUE"
        )
        params: list = [project_id, sheet_name]
        if financial_type is not None:
            sql += " AND financial_type = %s"
            params.append(financial_type)
        sql += " ORDER BY report_year DESC, report_month DESC LIMIT 1"

        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return (row[0], row[1]) if row else None


def _to_row(r: dict) -> FinancialRow:
    raw_value = r.get("value")
    return FinancialRow(
        project_id=r["project_id"],
        sheet_name=r["sheet_name"],
        report_month=r["report_month"],
        report_year=r["report_year"],
        financial_type=r.get("financial_type"),
        item_code=r.get("item_code"),
        data_type=r.get("data_type"),
        friendly_name=r.get("friendly_name"),
        category=r.get("category"),
        tier=r.get("tier"),
        value=float(raw_value) if raw_value is not None else None,
    )
