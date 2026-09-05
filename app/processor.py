import logging
import threading

from . import gemini_client, servicenow
from .schemas import IncidentPayload

logger = logging.getLogger(__name__)

# Single lock around check-and-add: two deliveries of the same sys_id must
# not both slip through, and the set is touched from worker threads.
_lock = threading.Lock()
PROCESSED_SYS_IDS: set[str] = set()


def mark_processed(sys_id: str) -> bool:
    """Record sys_id. Returns False if it was already seen (duplicate)."""
    with _lock:
        if sys_id in PROCESSED_SYS_IDS:
            return False
        PROCESSED_SYS_IDS.add(sys_id)
        return True


def clear_processed() -> None:
    with _lock:
        PROCESSED_SYS_IDS.clear()


async def process_incident_task(payload: IncidentPayload) -> None:
    # Never let a background failure take down the worker; log and move on.
    try:
        decision = await gemini_client.decide(payload)
        body = servicenow.build_writeback_payload(decision)
        logger.info("Incident %s decision=%s", payload.number, decision.decision)
        await servicenow.patch_incident(payload.incident_sys_id, body)
        logger.info("Incident %s write-back complete", payload.number)
    except Exception:
        logger.exception("Background processing failed for incident %s", payload.number)
