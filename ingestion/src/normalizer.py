"""
Normalizer: applies financial_type_map and heading_map lookups to ExtractedRows.

Produces dicts ready for insert_normalized_rows(), and tracks unmapped items.
Does NOT touch the database — that is the ingestion orchestrator's job.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .parser import ExtractedRow

log = logging.getLogger(__name__)


@dataclass
class NormalizeResult:
    rows: list[dict] = field(default_factory=list)
    unmapped_financial_types: set[str] = field(default_factory=set)
    unmapped_item_codes: set[str] = field(default_factory=set)


def normalize_rows(
    extracted: list[ExtractedRow],
    upload_id: str,
    project_id: str,
    financial_type_map: dict[str, str],
    heading_map: dict[str, dict],
) -> NormalizeResult:
    result = NormalizeResult()

    for row in extracted:
        financial_type = financial_type_map.get(row.raw_financial_type)
        if financial_type is None:
            result.unmapped_financial_types.add(row.raw_financial_type)

        heading = heading_map.get(row.item_code) if row.item_code else None
        if row.item_code and heading is None:
            result.unmapped_item_codes.add(row.item_code)

        result.rows.append({
            "upload_id": upload_id,
            "project_id": project_id,
            "sheet_name": row.sheet_name,
            "report_month": row.report_month,
            "report_year": row.report_year,
            "raw_financial_type": row.raw_financial_type,
            "financial_type": financial_type,
            "item_code": row.item_code,
            "data_type": heading["data_type"] if heading else None,
            "friendly_name": heading["friendly_name"] if heading else None,
            "category": heading["category"] if heading else None,
            "tier": heading["tier"] if heading else None,
            "value": row.value,
            "source_row_number": row.source_row_number,
            "source_cell_reference": row.source_cell_ref,
        })

    if result.unmapped_financial_types:
        log.warning(
            "Unmapped financial types (%d): %s",
            len(result.unmapped_financial_types),
            sorted(result.unmapped_financial_types),
        )
    if result.unmapped_item_codes:
        log.warning(
            "Unmapped item codes (%d): %s",
            len(result.unmapped_item_codes),
            sorted(result.unmapped_item_codes),
        )

    return result
