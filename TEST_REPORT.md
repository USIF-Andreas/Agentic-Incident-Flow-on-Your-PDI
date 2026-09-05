# Test Report — Agentic Incident Flow

Date: 2026-09-05 | PDI: `https://dev389551.service-now.com` | Model: `gemini-2.5-flash`
Public endpoint: `https://abhorrently-threadless-reina.ngrok-free.dev` (ngrok, authtoken configured)

## Summary

| # | Test | Expected | Actual | Status |
|---|------|----------|--------|--------|
| T1 | Rule-based fallback decisions (no key): printer / vague email / leave | respond / ask / escalate | respond / ask / escalate | ✅ PASS |
| T2 | Write-back payload mapping (respond/ask/escalate keys) | state+close_code+close_notes+comments / comments / work_notes | exact match | ✅ PASS |
| T3 | Pydantic rejection of `priority: 9` | validation error | rejected | ✅ PASS |
| T4 | Idempotency set (`mark_processed`/`is_duplicate`) | 2nd add returns False | confirmed | ✅ PASS |
| T5 | KB articles load | 5 articles | 5 lines loaded | ✅ PASS |
| T6 | `POST /webhook` first delivery (TestClient) | 202 in < 2 s | 202 in 0.053 s, background enqueued once | ✅ PASS |
| T7 | `POST /webhook` duplicate delivery | 202 `{"status":"duplicate"}`, no re-processing | exact match | ✅ PASS |
| T8 | Malformed payload / missing fields over HTTP | 422 / 422 | 422 / 422 | ✅ PASS |
| T9 | `GET /health` | `{"status":"ok"}` | exact match | ✅ PASS |
| T10 | Background task with no SN credentials | logged, worker survives | `RuntimeError` caught/logged, no crash | ✅ PASS |
| T11 | Live uvicorn `POST /webhook` (localhost) | 202 in < 2 s | 202 in 0.002 s | ✅ PASS |
| T12 | Live Gemini key check (printer incident) | `respond` + printer solution | `respond` / "Restart the printer and unplug the cable for 30 seconds." | ✅ PASS |
| T13 | ngrok tunnel + public `POST /webhook` | 202 in < 2 s via public URL | 202 in 0.11 s | ✅ PASS |
| T14 | E2E printer (`INC0010001`, 1st attempt) | Resolved with solution | decision=respond, **PATCH → 403** (see §Failure analysis) | ❌ FAIL → fixed |
| T15 | E2E printer retry (`INC0010002`) | Resolved with solution | state=Resolved, `close_code=Solution provided`, solution in comments, PATCH 200 | ✅ PASS |
| T16 | E2E vague email (`INC0010003`) | `ask`, stays open, question in comments | state=New, clarifying question in comments, PATCH 200 | ✅ PASS |
| T17 | E2E leave request (`INC0010004`) | `escalate`, stays open, reason in work_notes | state=New, escalation reason in work_notes, PATCH 200 | ✅ PASS |

Final ticket states (read back from PDI via Table API):
- `INC0010002`: state=Resolved, close_code="Solution provided",
  comments="Restart the printer and unplug the cable for 30 seconds."
- `INC0010003`: state=New,
  comments="Can you provide more details about the issue, such as any error messages or the email application you are using?"
- `INC0010004`: state=New,
  work_notes="Escalated by AI Agent: This is an HR request for annual leave approval, which is outside the scope of IT troubleshooting."

## Failure analysis (T14)

**Symptom:** `PATCH /api/now/table/incident/{sys_id}` with the `respond` payload returned
`HTTP 403 Forbidden`. The Gemini decision (`respond`) and delivery (202) were correct —
only the write-back failed.

**Isolation steps:**
1. `PATCH {work_notes}` only → `200 OK` → auth and PATCH verb are fine.
2. `PATCH {comments}` only → `200 OK`.
3. `PATCH {state:6, close_code:"Solved (Permanently)", close_notes}` only → `403` with body:
   `Data Policy Exception: The following fields are mandatory: Resolution code`.
4. Queried `sys_choice` (`name=incident^element=close_code`) → this PDI's valid values are
   `Solution provided`, `Resolved by caller`, `Duplicate`, etc. — **`Solved (Permanently)`
   does not exist here**, so the field was treated as empty and the Data Policy rejected
   the resolve transition.

**Fix (committed as `fix: use PDI-valid close_code 'Solution provided' …`):**
`app/servicenow.py` now sends `close_code: "Solution provided"`; `PLAN.md` §4.3 and
`README.md` document that `close_code` must be a valid `sys_choice` value on the target PDI.
Re-test (T15) returned `PATCH 200` and the ticket resolved.

**Side observation (not a failure):** creating incidents via the Table API also fires the
PDI Business Rule, so the flow ran before any manual webhook call — the manual re-POST
correctly returned `{"status":"duplicate"}` and was not re-processed (live proof of FR5).

## How to re-run

```bash
uvicorn app.main:app --reload --port 8000
ngrok http --url=abhorrently-threadless-reina.ngrok-free.dev 8000
# Then: Incidents → Create New in the PDI and watch the logs.
```
