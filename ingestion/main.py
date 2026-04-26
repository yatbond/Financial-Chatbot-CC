"""FastAPI ingestion service entry point."""

import logging
import re
import sys

import uvicorn
from fastapi import BackgroundTasks, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.config import INGESTION_PORT
from src.db import get_connection
from src.ingestion import run_ingestion
from src.postgres_data_provider import PostgresDataProvider
from src.resolver_service import build_resolver, resolve_and_execute

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

app = FastAPI(title="FinLens Ingestion Service")

_UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE,
)


# ── Ingest endpoint ───────────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    upload_id: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ingest")
def ingest(req: IngestRequest, background_tasks: BackgroundTasks):
    if not _UUID_RE.match(req.upload_id):
        return JSONResponse(
            {"error": "upload_id must be a valid UUID"},
            status_code=422,
        )
    background_tasks.add_task(run_ingestion, req.upload_id)
    return JSONResponse({"accepted": True, "upload_id": req.upload_id}, status_code=202)


# ── Query endpoint ────────────────────────────────────────────────────────────

class ContextPayload(BaseModel):
    project_id: str | None = None
    project_code: str | None = None
    project_name: str | None = None
    financial_type: str | None = None
    data_type: str | None = None
    sheet_name: str | None = None
    month: int | None = None
    year: int | None = None
    report_month: int | None = None
    report_year: int | None = None
    last_shortcut: str | None = None


class AmbiguityOptionPayload(BaseModel):
    label: str
    params: dict = {}


class QueryRequest(BaseModel):
    query: str
    project_id: str
    context: ContextPayload = ContextPayload()
    mode: str = "standard"
    selected_option_index: int | None = None
    prior_options: list[AmbiguityOptionPayload] | None = None


@app.post("/query")
def query_endpoint(req: QueryRequest):
    conn = get_connection()
    try:
        resolver, heading_map = build_resolver(conn)
        provider = PostgresDataProvider(conn)
        result = resolve_and_execute(
            query=req.query,
            project_id=req.project_id,
            context_dict=req.context.model_dump(),
            mode=req.mode,
            selected_option_index=req.selected_option_index,
            prior_options=(
                [o.model_dump() for o in req.prior_options]
                if req.prior_options else None
            ),
            resolver=resolver,
            provider=provider,
            heading_map=heading_map,
        )
        return JSONResponse(result)
    except Exception as exc:
        log.exception("Query resolution failed for project=%s query=%r", req.project_id, req.query)
        return JSONResponse({"type": "error", "message": f"Query failed: {type(exc).__name__}: {exc}"})
    finally:
        conn.close()


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=INGESTION_PORT, reload=False)
