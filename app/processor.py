"""Background task coordinator + idempotency guard (FR5, NFR3)."""

import logging
import threading

from . import gemini_client, servicenow
from .schemas import IncidentPayload

logger = logging.getLogger(__name__)

_lock = threading.Lock()
PROCESSED_SYS_IDS: set[str] = set()


def is_duplicate(sys_id: str) -> bool:
    with _lock:
        return sys_id in PROCESSED_SYS_IDS


def mark_processed(sys_id: str) -> bool:
    """Add sys_id to the cache. Returns False if it was already present."""
    with _lock:
        if sys_id in PROCESSED_SYS_IDS:
            return False
        PROCESSED_SYS_IDS.add(sys_id)
        return True


def clear_processed() -> None:
    """Test helper: reset the idempotency cache."""
    with _lock:
        PROCESSED_SYS_IDS.clear()


async def process_incident_task(payload: IncidentPayload) -> None:
    """Full background pipeline: Gemini decision -> ServiceNow write-back.

    Errors are caught and logged so the worker never crashes (NFR3).
    """
    try:
        decision = await gemini_client.decide(payload)
        body = servicenow.build_writeback_payload(decision)
        logger.info("Incident %s decision=%s", payload.number, decision.decision)
        await servicenow.patch_incident(payload.incident_sys_id, body)
        logger.info("Incident %s write-back complete", payload.number)
    except Exception:
        logger.exception("Background processing failed for incident %s", payload.number)
