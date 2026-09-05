import logging

import httpx

from .config import settings
from .schemas import DecisionResponse

logger = logging.getLogger(__name__)


def build_writeback_payload(decision: DecisionResponse) -> dict:
    if decision.decision == "respond":
        return {
            "state": "6",
            # close_code must be a real sys_choice value for incident.close_code
            # on the target PDI. "Solved (Permanently)" is not one on ours and
            # the resolve gets rejected (Data Policy: Resolution code mandatory).
            "close_code": "Solution provided",
            "close_notes": "Resolved automatically by AI Agent using Knowledge Base.",
            "comments": decision.message,
        }
    if decision.decision == "ask":
        return {"comments": decision.message}
    return {"work_notes": f"Escalated by AI Agent: {decision.message}"}


async def patch_incident(sys_id: str, data: dict) -> None:
    base = (settings.SN_INSTANCE_URL or "").rstrip("/")
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
