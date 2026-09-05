# Agentic Incident Flow on Your PDI

Automated IT incident triage: ServiceNow PDI → FastAPI webhook → Gemini 2.5 Flash decision → write-back to the same ticket. See `PLAN.md` for the full spec and `pdi_guide.md` for the no-experience PDI walkthrough.

The loop (all automatic, no manual steps between):

1. Incident created in PDI → async Business Rule POSTs JSON to `/webhook`.
2. FastAPI validates, returns `202 Accepted` in <2s, enqueues a background task.
3. Gemini decides `respond | ask | escalate` using only the 5 KB articles.
4. Service `PATCH`es the same incident (`state=6`+comments, comments, or work_notes).

## Prerequisites

- Python 3.11+
- A ServiceNow PDI (`https://developer.servicenow.com`, see `pdi_guide.md` Step 1)
- ngrok (free, for exposing port 8000)
- A free Gemini API key from Google AI Studio (no credit card): <https://aistudio.google.com>

## Setup

```bash
git clone <this-repo> && cd Agentic-Incident-Flow-on-Your-PDI
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your real values
```

`.env` fields:

| Var | Example |
| --- | --- |
| `GEMINI_API_KEY` | key from AI Studio |
| `SN_INSTANCE_URL` | `https://devXXXXXX.service-now.com` (no trailing slash) |
| `SN_USER` | `admin` |
| `SN_PASSWORD` | your PDI admin password |

> Without a real `GEMINI_API_KEY` the service still boots and uses a deterministic
> rule-based fallback so the three test tickets produce their expected decisions.
> With a real key, the Gemini LLM path is used.

## Run

```bash
uvicorn app.main:app --port 8000
ngrok http 8000   # copy the https URL, e.g. https://ab12cd34.ngrok-free.app
```

Health check: `GET http://localhost:8000/health` → `{"status":"ok"}`.

## ServiceNow wiring (summary — details in `pdi_guide.md`)

1. PDI → All → **Business Rules** → **New**: Name `Task0 - Send Incident to Agent`, Table `Incident [incident]`, Advanced ✔, When `after`, Insert ✔.
2. Advanced tab: paste `business_rule.js`, replacing `YOUR_ENDPOINT` with your ngrok URL **keeping** `/webhook` (e.g. `https://ab12cd34.ngrok-free.app/webhook`).
3. Submit. Create an Incident → watch FastAPI logs; the JSON payload (see `payload_contract.json`) should arrive in seconds. Debug via **System Logs > System Log > All**, search `Task0`.

## Verification

Manual curl (replace `xxx` with a real `sys_id` for a live write-back test):

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

Expected end-to-end outcomes (`test_incidents.json`):

| Test | Input | Expected decision | Ticket result |
| --- | --- | --- | --- |
| 1 Printer | "Printer not printing after office move" | `respond` | Resolved (`state=6`, solution in comments) |
| 2 Vague email | "Cannot send email" / "It just doesn't work." | `ask` | Still open, clarifying question in comments |
| 3 Leave request | "Request: annual leave approval" | `escalate` | Still open, reason in work_notes |

Idempotency: re-POST the same payload → `{"status":"duplicate",...}` (202) and no second write-back. Malformed payload (e.g. `priority: 9`) → `422`.

## Project layout

```text
app/            # config, schemas, main (webhook), gemini_client, servicenow, processor
data/kb_articles.json  # the 5 KB articles (also at repo root from the asset pack)
business_rule.js / payload_contract.json / test_incidents.json / pdi_guide.md  # asset pack (unchanged)
PLAN.md         # spec & build tracking
```

## Notes

- `work_notes` are internal; `comments` are customer-visible (`pdi_guide.md` Step 5).
- PDI sleeps after inactivity — wake it in the developer portal if the trigger stops.
- ngrok URL changes on restart — update the Business Rule endpoint each time.
