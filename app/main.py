"""FastAPI entrypoint (FR2, NFR1)."""

import logging
from typing import Any

from fastapi import BackgroundTasks, FastAPI, status
from fastapi.responses import JSONResponse

from . import processor
from .schemas import IncidentPayload

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Agentic Incident Flow", version="1.0.0")


@app.get("/", tags=["health"])
async def root() -> dict[str, str]:
    return {"service": "agentic-incident-flow", "status": "ok"}


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook", status_code=status.HTTP_202_ACCEPTED, tags=["webhook"])
async def webhook(payload: IncidentPayload, background_tasks: BackgroundTasks) -> Any:
    """Validate payload, enqueue async work, respond 202 in <2s (NFR1).

    Duplicate sys_ids are acknowledged but not re-processed (FR5).
    Malformed payloads are rejected with 422 by Pydantic (NFR3).
    """
    if not processor.mark_processed(payload.incident_sys_id):
        logger.info("Duplicate webhook ignored for %s", payload.incident_sys_id)
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"status": "duplicate", "incident_sys_id": payload.incident_sys_id},
        )
    background_tasks.add_task(processor.process_incident_task, payload)
    logger.info("Accepted webhook for incident %s", payload.number)
    return {"status": "accepted", "incident_sys_id": payload.incident_sys_id}
