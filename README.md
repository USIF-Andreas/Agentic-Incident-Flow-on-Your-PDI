# Agentic Incident Flow on Your PDI

This is my Task 0 submission — a small ServiceNow incident triage pipeline. The idea: when a new incident is created on a ServiceNow PDI, a Business Rule POSTs it to a FastAPI webhook I built, Gemini looks at the ticket against 5 knowledge base articles and decides what to do with it, and then the service writes the decision back to the same ticket.

## How it works

1. Incident gets created in the PDI → a Business Rule (async, after insert) POSTs the JSON to `/webhook`.
2. FastAPI validates the payload and immediately returns `202 Accepted` (under 2s), then does the actual work in a background task so ServiceNow doesn't time out waiting on us.
3. Gemini looks at the ticket and picks one of three actions — `respond`, `ask`, or `escalate` — plus a message. It's only allowed to use the 5 KB articles, nothing outside that.
4. Based on the decision, the service PATCHes the incident back:
   - `respond` → closes it (`state=6`), puts the solution in the comments
   - `ask` → leaves it open, adds a clarifying question in the comments
   - `escalate` → leaves it open, adds the reason to work notes

## Before you run it

You'll need:
- Python 3.11+
- A ServiceNow PDI (get one free at `https://developer.servicenow.com`)
- ngrok (free tier works fine — needed to expose port 8000 to ServiceNow)
- A Gemini API key from Google AI Studio (`https://aistudio.google.com`)

## Setup

```bash
git clone <this-repo> && cd Agentic-Incident-Flow-on-Your-PDI
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Then fill in `.env`:

```
GEMINI_API_KEY=your key from AI Studio
SN_INSTANCE_URL=https://devXXXXXX.service-now.com   # no trailing slash
SN_USER=admin
SN_PASSWORD=your PDI admin password
```

One thing worth mentioning — if you don't set a real `GEMINI_API_KEY`, the service doesn't crash. It just falls back to a simple rule-based decision so the three sample tickets still resolve the way they're supposed to. Handy for testing without burning API calls.

## Running it

```bash
uvicorn app.main:app --port 8000
ngrok http 8000
```

Grab the https URL ngrok gives you (something like `https://ab12cd34.ngrok-free.app`) — you'll need it for the ServiceNow side.

Quick sanity check: `GET http://localhost:8000/health` should return `{"status":"ok"}`.

## Wiring it up in ServiceNow

1. In the PDI, go to **System Definition > Business Rules > New**.
   - Name: `Task0 - Send Incident to Agent`
   - Table: `Incident [incident]`
   - Turn on Advanced, set When to `after`, check Insert
2. In the Advanced tab, paste in `business_rule.js`. Swap `YOUR_ENDPOINT` for your ngrok URL (keep the `/webhook` path at the end).
3. Save it, then create a test incident and watch your FastAPI terminal — the payload should show up within a couple seconds. If nothing happens, check **System Logs > System Log > All** and filter for `Task0`.

## Testing it manually

```bash
curl -s -X POST localhost:8000/webhook -H 'Content-Type: application/json' -d '{
  "incident_sys_id": "1c741bd70b2322007518478d83673af3",
  "number": "INC0010001",
  "short_description": "Printer not printing after office move",
  "description": "It was working yesterday. I tried turning it off and on.",
  "priority": 3
}' -w '\nHTTP %{http_code} time %{time_total}s\n'
```

That should come back `202` in well under 2 seconds with `{"status":"accepted",...}`.

I tested against three scenarios (see `test_incidents.json`):

- **Printer issue** ("Printer not printing after office move") → resolved automatically, `close_code` set to `Solution provided`, solution written to comments.
- **Vague email complaint** ("Cannot send email" / "It just doesn't work") → left open, Gemini asks a clarifying question in the comments instead of guessing.
- **Leave request** ("Request: annual leave approval") → left open, escalated with the reason in work notes since it's outside what the KB articles cover.

A couple of edge cases I handled: re-sending the same payload just returns `{"status":"duplicate",...}` without touching the ticket again, and a bad payload (e.g. `priority: 9`) gets rejected with a `422` instead of silently failing.

One gotcha I ran into: `close_code` has to match an actual `sys_choice` value configured on the PDI's `incident.close_code` field — mine only accepts `Solution provided`, so anything else trips the Data Policy and comes back as a `403`. Worth checking your own PDI's choices before assuming the value I used will work.

## Project layout

```
app/                     # config, schemas, main.py (the webhook), gemini_client, servicenow, processor
data/kb_articles.json    # the 5 KB articles the agent is grounded on
business_rule.js
payload_contract.json
test_incidents.json
pdi_guide.md             # step-by-step PDI setup notes from the original task assets
```

## Notes to self

- `work_notes` are internal only, `comments` show up to the customer — mixed these up more than once while testing.
- PDIs go to sleep after a while if you're not using them, so if the trigger suddenly stops firing, go wake the instance up from the developer portal first before debugging anything else.
- The ngrok URL changes every time you restart it on the free tier, so remember to update the Business Rule endpoint each time or you'll be staring at silence in the logs for no reason.

## Reflection & Future Improvements

A few things that work fine for a prototype but should be handled differently in production:

1. **Expand KB coverage and sync directly with ServiceNow Knowledge**  
   The system currently relies on just 5 static articles in a local JSON file, which forces almost anything outside basic printers/passwords into an escalation. In a real environment, the service should periodically sync with ServiceNow's native Knowledge Base (`kb_knowledge` table) or ingest common internal IT SOPs (VPN troubleshooting, software provisioning, SSO issues). That would cut down unnecessary human escalations and allow the agent to resolve a much wider variety of everyday tickets.

2. **Redis for idempotency instead of in-memory set**  
   Right now the deduplication relies on a plain Python `set` with a thread lock. It works for a single worker, but if the process restarts or we scale horizontally to multiple Uvicorn workers, that state is lost. Moving this to Redis with a basic `SETNX` and a 24-hour TTL would make it stateless and safe across restarts and multiple instances.

3. **A real job queue instead of FastAPI BackgroundTasks**  
   `BackgroundTasks` runs in-memory. If the app gets killed while waiting on Gemini or the ServiceNow PATCH call, that job is simply dropped. Offloading incoming incidents to Celery, ARQ, or BullMQ backed by Redis/RabbitMQ would give us task persistence, automatic retries with backoff for network drops, and a dead-letter queue for bad tickets.

4. **RAG retrieval instead of dumping all KBs in the prompt**  
   Hardcoding the 5 KB articles directly into the prompt is fine for a fixed assignment, but it doesn't scale. If the IT desk has hundreds of runbooks, we'd need to store them in a vector DB (like pgvector or Qdrant) and only fetch the top 2-3 relevant chunks per incident to keep token costs down and prevent context clutter.
