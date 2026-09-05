# Implementation & Architectural Plan: Agentic Incident Flow

## 1. Project Overview & Objective
This service automates IT incident triage on a ServiceNow Personal Developer Instance (PDI) using Google's Gemini LLM.
When an incident is created in ServiceNow, an asynchronous Business Rule triggers a FastAPI webhook. The service evaluates the ticket against five predefined Knowledge Base (KB) articles and performs an automated write-back into the same incident via ServiceNow REST Table API.

## 2. Requirements Matrix

### Functional Requirements (FR)
| ID | Requirement | Target Implementation |
| :--- | :--- | :--- |
| **FR1** | **Event Capture** | PDI Business Rule triggers on `incident` `insert` (after) and issues an async POST request to the public webhook URL. |
| **FR2** | **Webhook Service** | FastAPI endpoint `POST /webhook` validates the JSON payload and responds immediately with `202 Accepted`. Heavy tasks run asynchronously. |
| **FR3** | **Gemini Decision** | LLM evaluates the incident text strictly against 5 KB articles, outputting structured JSON: `{"decision": "...", "message": "..."}`. Out-of-scope issues trigger `escalate`. |
| **FR4** | **Write-back** | ServiceNow Table API `PATCH` updates the ticket: `respond` (resolve + comments), `ask` (comments), `escalate` (work_notes). |
| **FR5** | **No Double Processing** | In-memory thread-safe `Set` tracking processed `incident_sys_id` values to ignore duplicate webhooks. |
| **FR6** | **Test Ticket Compliance** | System reproduces expected outcomes for printer (respond), vague email (ask), and leave request (escalate). |

### Non-Functional Requirements (NFR)
| ID | Requirement | Target Implementation |
| :--- | :--- | :--- |
| **NFR1** | **Fast Response Time** | Webhook endpoint responds in `< 2 seconds` by offloading LLM inference and ServiceNow write-back to `fastapi.BackgroundTasks`. |
| **NFR2** | **Zero Secrets in VCS** | All credentials (`GEMINI_API_KEY`, `SN_INSTANCE_URL`, `SN_USER`, `SN_PASSWORD`) stored in `.env`. Included `.env.example` in repo. |
| **NFR3** | **Fault Tolerance & Robustness** | Pydantic validation handles malformed payloads gracefully with `422`. Background task errors are caught and logged without crashing the worker. |
| **NFR4** | **Reproducibility** | Complete, clean `README.md`, fixed `requirements.txt`, and automated setup instructions. |
| **NFR5** | **Atomic Commit History** | Logical git history reflecting discrete milestones rather than a single bulk commit. |

## 3. Architecture & Data Flow

```text
[ ServiceNow PDI ]
│
│ (1) Incident Created -> Business Rule (Async HTTP POST)
▼
[ ngrok Tunnel ]
│
▼
[ FastAPI App (POST /webhook) ]
│
├─► Check In-Memory Idempotency Cache (FR5)
├─► Enqueue Background Task (FR2, NFR1)
└─► Return HTTP 202 Accepted (Immediate response < 2s)
│
▼ (Asynchronous Background Execution)
[ LLM Reasoning Worker ]
│
├─► Load & inject 5 KB Articles (data/kb_articles.json)
├─► Call Gemini 2.5 Flash via google-genai SDK
│   └─ Strict JSON Schema: {decision, message}
▼
[ ServiceNow Write-Back Client ]
│
└─► HTTP PATCH /api/now/table/incident/{incident_sys_id}
    ├─ respond  -> Close incident (state=6) + solution in comments
    ├─ ask      -> Post question in comments
    └─ escalate -> Post escalation reason in work_notes
```

## 4. Contract Specifications

### 4.1. Webhook Input Contract (`POST /webhook`)
```json
{
  "incident_sys_id": "string (32-char hex)",
  "number": "string (e.g. INC0010001)",
  "short_description": "string",
  "description": "string (optional/nullable)",
  "priority": "integer (1 to 5)"
}
```

### 4.2. Gemini Structured Output Schema
```json
{
  "decision": "respond | ask | escalate",
  "message": "string"
}
```

### 4.3. ServiceNow Write-Back Mapping (Table API)
Target: `PATCH https://<INSTANCE>.service-now.com/api/now/table/incident/{incident_sys_id}`

When `decision == "respond"`:
```json
{
  "state": "6",
  "close_code": "Solution provided",
  "close_notes": "Resolved automatically by AI Agent using Knowledge Base.",
  "comments": "<Gemini Message>"
}
```
> `close_code` must be a valid `sys_choice` value for `incident.close_code` on the target PDI (verified: `Solution provided`). Other values trip the PDI Data Policy ("Resolution code is mandatory") → HTTP 403.
When `decision == "ask"`:
```json
{
  "comments": "<Gemini Message>"
}
```
When `decision == "escalate"`:
```json
{
  "work_notes": "Escalated by AI Agent: <Gemini Message>"
}
```

## 5. Repository File Structure
```text
incident-flow/
├── app/
│   ├── __init__.py
│   ├── config.py           # Pydantic Settings / Environment configuration
│   ├── schemas.py          # Pydantic models for incoming payload & LLM response
│   ├── gemini_client.py    # Google GenAI integration & prompt engineering
│   ├── servicenow.py       # REST API integration with ServiceNow
│   ├── processor.py        # Background task coordinator & idempotency logic
│   └── main.py             # FastAPI entrypoint and router
├── data/
│   └── kb_articles.json    # The 5 knowledge base articles
├── .env.example            # Sample environment variables template
├── .gitignore              # Git ignore rules (.env, __pycache__, etc.)
├── requirements.txt        # Frozen dependencies
├── PLAN.md                 # System specification and tracking
└── README.md               # Setup and verification guide
```

## 6. Detailed Implementation Steps

### Phase 1: Environment Setup & Project Foundation
- [x] Initialize Git repository.
- [x] Create `.gitignore` (ignore `.env`, `venv/`, `__pycache__`).
- [x] Create `.env.example` defining `GEMINI_API_KEY`, `SN_INSTANCE_URL`, `SN_USER`, `SN_PASSWORD`.
- [x] Populate `data/kb_articles.json` with the 5 provided articles.
- [x] Pin dependencies in `requirements.txt`.

Git Commit: `chore: initialize repository structure and dependencies`

### Phase 2: Core Webhook & Idempotency Layer
- [x] `app/config.py`: typed settings loader using `pydantic_settings.BaseSettings`.
- [x] `app/schemas.py`: `IncidentPayload` + `DecisionResponse` models.
- [x] `app/main.py`: `POST /webhook` with `202 Accepted`, in-memory idempotency guard, `BackgroundTasks`.

Git Commit: `feat: implement webhook endpoint with payload validation and idempotency`

### Phase 3: Gemini Decision Engine
- [x] `app/gemini_client.py`: `genai.Client`, zero-shot KB-grounded prompt, `respond`/`ask`/`escalate` boundaries, `temperature=0.0`, structured JSON via `response_schema=DecisionResponse`.

Git Commit: `feat: integrate gemini client with structured json outputs and kb grounding`

### Phase 4: ServiceNow Write-Back Integration
- [x] `app/servicenow.py`: `httpx.AsyncClient` with BasicAuth, `patch_incident`, decision-to-payload mapping.
- [x] `app/processor.py`: Gemini → ServiceNow pipeline in `process_incident_task` with try/except logging.

Git Commit: `feat: implement servicenow rest write-back mechanism`

### Phase 5: ServiceNow Configuration & End-to-End Verification
- [x] Configure ServiceNow Business Rule (see `pdi_guide.md` + `business_rule.js`, endpoint `<ngrok_url>/webhook`).
- [x] Start local server: `uvicorn app.main:app --port 8000`.
- [x] Expose via ngrok: `ngrok http 8000`.
- [x] Test cases: printer → respond/resolved; vague email → ask/comment; leave → escalate/work note.
- [x] Idempotency: duplicate payload bypassed.
- [x] Finalize `README.md`.

Git Commit: `docs: finalize documentation and end-to-end verification guide`
