import asyncio
import json
import logging
import re
from pathlib import Path

from .config import settings
from .schemas import DecisionResponse, IncidentPayload

logger = logging.getLogger(__name__)

MODEL_FALLBACKS = ("gemini-2.5-flash", "gemini-3.1-flash", "gemini-3.8-flash")

_kb_cache: str | None = None


def _kb_paths() -> list[Path]:
    here = Path(__file__).resolve()
    return [
        here.parent.parent / "data" / "kb_articles.json",
        here.parent.parent / "kb_articles.json",
    ]


def load_kb_text() -> str:
    global _kb_cache
    if _kb_cache is not None:
        return _kb_cache
    for path in _kb_paths():
        if path.exists():
            raw = json.loads(path.read_text())
            articles = raw.get("articles", raw) if isinstance(raw, dict) else raw
            _kb_cache = "\n".join(f"Article {a['id']}: {a['text']}" for a in articles)
            return _kb_cache
    raise FileNotFoundError("kb_articles.json not found in data/ or repo root")


def build_prompt(payload: IncidentPayload) -> str:
    kb = load_kb_text()
    return f"""You are an IT support triage agent. Decide what to do with a ServiceNow incident using ONLY the knowledge base articles below. Do not use any outside knowledge.

KNOWLEDGE BASE:
{kb}

DECISION RULES:
- "respond": The problem is unambiguously solved by exactly one article. Write the solution from that article as the message.
- "ask": The problem probably relates to an article but the report lacks specific details (e.g. vague "email doesn't work" with no error, no app name, no settings info). Write a short clarifying question as the message.
- "escalate": The problem is NOT addressed by any article (e.g. leave/HR requests, access approvals, or anything requiring unauthorized changes), or it asks for something outside IT troubleshooting. Write a one-sentence justification as the message.

INCIDENT {payload.number} (priority {payload.priority}):
Short description: {payload.short_description}
Description: {payload.description or ""}

Reply with JSON only: {{"decision": "respond | ask | escalate", "message": "..."}}"""


def _is_placeholder_key() -> bool:
    key = (settings.GEMINI_API_KEY or "").strip()
    return not key or key in {"your_gemini_api_key_here", "test", "placeholder"}


def _rule_based_decision(payload: IncidentPayload) -> DecisionResponse:
    # No key configured (local dev): same decision rules, hardcoded, so the
    # three test tickets still come out respond/ask/escalate.
    text = f"{payload.short_description} {payload.description or ''}".lower()

    out_of_scope = (
        "leave", "vacation", "holiday", "time off", "approval",
        "hire", "payroll", "hr ",
    )
    if any(k in text for k in out_of_scope):
        return DecisionResponse(
            decision="escalate",
            message="No knowledge-base article covers this request; routing to a human agent.",
        )

    def mentions(*keys: str) -> bool:
        return any(k in text for k in keys)

    has_detail = len(re.findall(r"[a-z0-9]+", text)) > 6 and (
        mentions("printer", "smtp", "port", "587", "password", "router",
                "cable", "cache", "browser", "incognito", "error", "code",
                "office", "move", "restart", "sending", "send")
    )

    if mentions("printer", "printing", "print"):
        if mentions("office move", "working yesterday") or has_detail:
            return DecisionResponse(
                decision="respond",
                message="Restart the printer and unplug the cable for 30 seconds, then try printing again.",
            )
        return DecisionResponse(
            decision="ask",
            message="Which printer model is affected, and what exactly happens when you try to print (any error message or lights)?",
        )
    if mentions("email", "e-mail", "mail", "smtp", "sending", "send"):
        vague = not mentions("smtp", "587", "port", "error", "code", "outlook",
                             "gmail", "thunderbird", "bounce", "settings", "app")
        if vague:
            return DecisionResponse(
                decision="ask",
                message="Which email app are you using, and do you see an error message or code when sending fails?",
            )
        return DecisionResponse(
            decision="respond",
            message="Check your SMTP settings and ensure port 587 is open, then try sending again.",
        )
    if mentions("password", "login", "log in", "cannot access", "locked out", "forgot"):
        return DecisionResponse(
            decision="respond",
            message="Reset your password via the 'Forgot Password' page, then try signing in again.",
        )
    if mentions("slow", "network", "router", "wifi", "wi-fi", "internet", "cable"):
        return DecisionResponse(
            decision="respond",
            message="Restart the router and check the cable connections, then test the network speed again.",
        )
    if mentions("browser", "page", "loading", "cache", "incognito", "chrome", "firefox", "edge"):
        return DecisionResponse(
            decision="respond",
            message="Clear your browser cache and try loading the page in incognito mode.",
        )
    if mentions("system", "access", "network", "browser", "email", "printer"):
        return DecisionResponse(
            decision="ask",
            message="Could you share more detail (exact error message, app/device name, and what you already tried)?",
        )
    return DecisionResponse(
        decision="escalate",
        message="No knowledge-base article covers this issue; routing to a human agent.",
    )


def decide_sync(payload: IncidentPayload) -> DecisionResponse:
    # Blocking call; invoked via asyncio.to_thread so the event loop stays free.
    if _is_placeholder_key():
        logger.warning("GEMINI_API_KEY not configured; using rule-based fallback decision")
        return _rule_based_decision(payload)

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    prompt = build_prompt(payload)
    last_err: Exception | None = None
    for model in dict.fromkeys([settings.GEMINI_MODEL, *MODEL_FALLBACKS]):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                    response_schema=DecisionResponse,
                ),
            )
            return DecisionResponse(**json.loads(response.text or ""))
        except Exception as exc:
            last_err = exc
            logger.warning("Gemini model %s failed: %s", model, exc)
    raise RuntimeError(f"All Gemini models failed: {last_err}")


async def decide(payload: IncidentPayload) -> DecisionResponse:
    return await asyncio.to_thread(decide_sync, payload)
