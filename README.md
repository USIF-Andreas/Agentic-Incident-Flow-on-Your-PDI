# Agentic Incident Flow on Your PDI

ServiceNow incident triage: a PDI Business Rule POSTs new incidents to a FastAPI webhook, Gemini classifies each one against 5 KB articles, and the service writes the outcome back to the same ticket. Spec in `PLAN.md`, PDI steps in `pdi_guide.md`, results in `TEST_REPORT.md`.

## Architecture

1. Incident created in PDI → async Business Rule POSTs JSON to `/webhook`.
2. FastAPI validates, returns `202 Accepted` in <2s, handles the rest in a background task.
3. Gemini returns `respond | ask | escalate` plus a message, grounded in the 5 KB articles only.
4. Service `PATCH`es the incident: `respond` closes it (`state=6`) with the solution in comments, `ask` leaves it open with a clarifying question in comments, `escalate` leaves it open with the reason in work notes.

## Prerequisites

- Python 3.11+
- A ServiceNow PDI (`https://developer.servicenow.com`, see `pdi_guide.md` Step 1)
- ngrok (free tier is enough, to expose port 8000)
- A Gemini API key from Google AI Studio: <https://aistudio.google.com>

## Environment Variables

Copy `.env.example` to `.env` and fill in:

| Var | Value |
| --- | --- |
| `GEMINI_API_KEY` | key from AI Studio |
| `SN_INSTANCE_URL` | `https://devXXXXXX.service-now.com` (no trailing slash) |
| `SN_USER` | `admin` |
| `SN_PASSWORD` | PDI admin password |

Without a real `GEMINI_API_KEY` the service still runs: it falls back to a deterministic rule-based decision so the three test tickets still produce their expected outcomes.

## Setup

```bash
git clone <this-repo> && cd Agentic-Incident-Flow-on-Your-PDI
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your values
```

## Run

```bash
uvicorn app.main:app --port 8000
ngrok http 8000   # note the https URL, e.g. https://ab12cd34.ngrok-free.app
```

Health check: `GET http://localhost:8000/health` → `{"status":"ok"}`.

## ServiceNow wiring (summary — details in `pdi_guide.md`)

1. PDI → All → **Business Rules** → **New**: Name `Task0 - Send Incident to Agent`, Table `Incident [incident]`, Advanced on, When `after`, Insert on.
2. Advanced tab: paste `business_rule.js`, replacing `YOUR_ENDPOINT` with the ngrok URL, keeping `/webhook` (e.g. `https://ab12cd34.ngrok-free.app/webhook`).
3. Submit. Create an incident and watch the FastAPI logs — the payload (see `payload_contract.json`) should arrive in seconds. If not, check **System Logs > System Log > All** for `Task0`.

## Verification

```bash
curl -s -X POST localhost:8000/webhook -H 'Content-Type: application/json' -d '{
  "incident_sys_id": "1c741bd70b2322007518478d83673af3",
  "number": "INC0010001",
  "short_description": "Printer not printing after office move",
  "description": "It was working yesterday. I tried turning it off and on.",
  "priority": 3
}' -w '\nHTTP %{http_code} time %{time_total}s\n'
# → {"status":"accepted",...} HTTP 202 in well under 2s
```

Expected outcomes (`test_incidents.json`):

| Test | Input | Decision | Ticket result |
| --- | --- | --- | --- |
| 1 Printer | "Printer not printing after office move" | `respond` | Resolved (`state=6`, `close_code="Solution provided"`, solution in comments) |
| 2 Vague email | "Cannot send email" / "It just doesn't work." | `ask` | Still open, clarifying question in comments |
| 3 Leave request | "Request: annual leave approval" | `escalate` | Still open, reason in work_notes |

Re-POSTing the same payload returns `{"status":"duplicate",...}` (202) with no second write-back. Bad payloads (e.g. `priority: 9`) return `422`.

Note: `close_code` must be a valid `sys_choice` value for `incident.close_code` on the target PDI — ours only accepts values like `Solution provided`, anything else trips its Data Policy with a 403.

## Project layout

```text
app/            # config, schemas, main (webhook), gemini_client, servicenow, processor
data/kb_articles.json  # the 5 KB articles (also at repo root from the asset pack)
business_rule.js / payload_contract.json / test_incidents.json / pdi_guide.md  # asset pack, unchanged
PLAN.md / TEST_REPORT.md
```

## Notes

- `work_notes` are internal; `comments` are customer-visible (`pdi_guide.md` Step 5).
- PDIs sleep after inactivity — wake the instance in the developer portal if the trigger stops.
- The ngrok URL changes on restart — update the Business Rule endpoint each time.
