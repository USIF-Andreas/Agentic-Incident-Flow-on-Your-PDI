"""ServiceNow Table API write-back client (FR4)."""

import logging

import httpx

from .config import settings
from .schemas import DecisionResponse

logger = logging.getLogger(__name__)


def build_writeback_payload(decision: DecisionResponse) -> dict:
    """Map a Gemini decision to a PATCH body (contract section 4.3)."""
    if decision.decision == "respond":
        return {
            "state": "6",
            # NOTE: must be a valid sys_choice value for incident.close_code
            # on the target PDI (e.g. "Solution provided"). Values like
            # "Solved (Permanently)" are rejected by this PDI's Data Policy
            # ("Resolution code is mandatory") with HTTP 403.
            "close_code": "Solution provided",
            "close_notes": "Resolved automatically by AI Agent using Knowledge Base.",
            "comments": decision.message,
        }
    if decision.decision == "ask":
        return {"comments": decision.message}
    return {"work_notes": f"Escalated by AI Agent: {decision.message}"}


def _base_url() -> str:
    return (settings.SN_INSTANCE_URL or "").rstrip("/")


async def patch_incident(sys_id: str, data: dict) -> None:
    """PATCH /api/now/table/incident/{sys_id}. Raises on HTTP error."""
    base = _base_url()
    if not base or not settings.SN_USER or not settings.SN_PASSWORD:
        raise RuntimeError("ServiceNow credentials (SN_INSTANCE_URL/SN_USER/SN_PASSWORD) are not configured")
    url = f"{base}/api/now/table/incident/{sys_id}"
    async with httpx.AsyncClient(
        auth=(settings.SN_USER, settings.SN_PASSWORD),
        timeout=settings.SN_TIMEOUT_SECONDS,
    ) as client:
        resp = await client.patch(
            url,
            json=data,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        logger.info("ServiceNow PATCH %s -> %s", sys_id, resp.status_code)
        resp.raise_for_status()
