import logging

from fastapi import BackgroundTasks, FastAPI, status
from fastapi.responses import JSONResponse

from . import processor
from .schemas import IncidentPayload

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Agentic Incident Flow", version="1.0.0")


@app.get("/", tags=["health"])
async def root():
    return {"service": "agentic-incident-flow", "status": "ok"}


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}


@app.post("/webhook", status_code=status.HTTP_202_ACCEPTED, tags=["webhook"])
async def webhook(payload: IncidentPayload, background_tasks: BackgroundTasks):
    # mark_processed checks and records under one lock; a separate
    # "seen before?" lookup here would race with concurrent deliveries.
    if not processor.mark_processed(payload.incident_sys_id):
        logger.info("Duplicate webhook ignored for %s", payload.incident_sys_id)
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"status": "duplicate", "incident_sys_id": payload.incident_sys_id},
        )
    background_tasks.add_task(processor.process_incident_task, payload)
    logger.info("Accepted webhook for incident %s", payload.number)
    return {"status": "accepted", "incident_sys_id": payload.incident_sys_id}
