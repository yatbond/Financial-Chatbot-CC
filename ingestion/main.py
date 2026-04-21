"""FastAPI ingestion service entry point."""

import logging
import sys

import uvicorn
from fastapi import BackgroundTasks, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.config import INGESTION_PORT
from src.ingestion import run_ingestion

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    stream=sys.stdout,
)

app = FastAPI(title="FinLens Ingestion Service")


class IngestRequest(BaseModel):
    upload_id: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ingest")
def ingest(req: IngestRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(run_ingestion, req.upload_id)
    return JSONResponse({"accepted": True, "upload_id": req.upload_id}, status_code=202)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=INGESTION_PORT, reload=False)
