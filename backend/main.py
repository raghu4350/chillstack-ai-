"""
backend/main.py
---------------
FastAPI backend for ResolveDesk — AI Internal Service Agent.

Wraps all existing resolvedesk/ Python modules as REST API endpoints.
The React frontend (port 5173) calls these endpoints.

Run with:
    uvicorn backend.main:app --reload --port 8000

Swagger UI: http://localhost:8000/docs
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env", override=True)
except ImportError:
    pass

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from resolvedesk.database import (
    init_db, get_case_state, upsert_case_state, add_clarification,
    get_clarifications, get_pending_plan, append_audit, get_audit_log,
    export_audit_json, get_conversation, add_message, clear_conversation, DB_PATH,
)
from resolvedesk.data import (
    get_all_cases, get_requests, get_tickets, get_policies,
    get_request_by_id, get_ticket_by_id, get_policy_by_id,
)
from resolvedesk.config import (
    TOTAL_POLICIES, TOTAL_REQUESTS, TOTAL_TICKETS,
    ACTIVE_TICKETS, CLOSED_TICKETS, TOTAL_SOURCE_RECORDS, COMPANY_NAME,
)
from resolvedesk.agent import run_agent, run_offline
from resolvedesk.rules import detect_topic, validate_plan

init_db()

app = FastAPI(title="ResolveDesk API", description="AI Internal Service Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ClarificationRequest(BaseModel):
    clarification: str
    structured_data: dict | None = None
    reported_by: str = "operator"

class RecordActionRequest(BaseModel):
    proposed_action: str
    proposed_status: str
    policy_ids: list[str] = []
    topic: str = ""
    mode: str = "groq"
    summary: str = ""

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "ResolveDesk API"}

@app.get("/api/stats")
def get_stats():
    return {
        "total_policies": TOTAL_POLICIES,
        "total_requests": TOTAL_REQUESTS,
        "total_tickets": TOTAL_TICKETS,
        "active_tickets": ACTIVE_TICKETS,
        "closed_tickets": CLOSED_TICKETS,
        "total_source_records": TOTAL_SOURCE_RECORDS,
        "company_name": COMPANY_NAME,
        "groq_key_set": bool(os.environ.get("GROQ_API_KEY", "").strip()),
        "groq_model": os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
    }

@app.get("/api/cases")
def list_cases(include_closed: bool = True):
    cases = get_all_cases()
    if not include_closed:
        cases = [c for c in cases if not c.get("is_closed", False)]
    for c in cases:
        c["db_state"] = get_case_state(c["id"])
    return {"cases": cases, "count": len(cases)}

@app.get("/api/cases/{case_id}")
def get_case(case_id: str):
    cid = case_id.upper().strip()
    record = get_request_by_id(cid) or get_ticket_by_id(cid)
    if not record:
        raise HTTPException(status_code=404, detail=f"Case '{cid}' not found.")
    topic = record.get("topic", detect_topic(record.get("request", record.get("issue_summary", ""))))
    return {
        "case": record,
        "db_state": get_case_state(cid),
        "clarifications": get_clarifications(cid),
        "conversation": get_conversation(cid),
        "topic": topic,
        "is_closed": record.get("is_closed", False),
        "record_type": record.get("record_type", "request"),
    }

@app.get("/api/policies")
def list_policies():
    p = get_policies()
    return {"policies": p, "count": len(p)}

@app.get("/api/policies/{policy_id}")
def get_policy(policy_id: str):
    p = get_policy_by_id(policy_id.upper())
    if not p:
        raise HTTPException(status_code=404, detail=f"Policy '{policy_id}' not found.")
    return p

@app.get("/api/audit")
def get_audit(case_id: str | None = None):
    records = get_audit_log(case_id=case_id.upper() if case_id else None)
    return {"records": records, "count": len(records)}

@app.get("/api/audit/export")
def export_audit():
    return {"json": export_audit_json()}

@app.post("/api/analyse/{case_id}")
def analyse_case(case_id: str):
    cid = case_id.upper().strip()
    api_key = os.environ.get("GROQ_API_KEY", "")
    model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
    result = run_agent(case_id=cid, api_key=api_key, model=model)
    return {"mode": result.mode, "success": result.success, "plan": result.plan, "trace": result.trace, "error": result.error, "questions": result.questions}

@app.post("/api/analyse/{case_id}/offline")
def analyse_case_offline(case_id: str):
    cid = case_id.upper().strip()
    result = run_offline(cid)
    return {"mode": result.mode, "success": result.success, "plan": result.plan, "trace": result.trace, "error": result.error, "questions": result.questions}

@app.post("/api/cases/{case_id}/clarification")
def add_case_clarification(case_id: str, body: ClarificationRequest):
    cid = case_id.upper().strip()
    if not body.clarification.strip():
        raise HTTPException(status_code=400, detail="Clarification text is required.")
    row_id = add_clarification(case_id=cid, clarification=body.clarification.strip(), structured_data=body.structured_data, reported_by=body.reported_by)
    append_audit(case_id=cid, action_type="clarification_added", description=f"Clarification: {body.clarification.strip()[:100]}")
    return {"ok": True, "clarification_id": row_id}

@app.post("/api/cases/{case_id}/record")
def record_case_action(case_id: str, body: RecordActionRequest):
    cid = case_id.upper().strip()
    record = get_request_by_id(cid) or get_ticket_by_id(cid)
    if not record:
        raise HTTPException(status_code=404, detail=f"Case '{cid}' not found.")
    if record.get("is_closed", False):
        raise HTTPException(status_code=400, detail="Cannot record action on a closed case.")
    db_state = get_case_state(cid)
    old_status = (db_state or {}).get("current_status") or record.get("initial_action") or record.get("source_status") or "Not started"
    new_status = body.proposed_status
    rec_type = record.get("record_type", "request")
    source_status = record.get("initial_action") or record.get("source_status") or "Not started"
    upsert_case_state(case_id=cid, record_type=rec_type, source_status=source_status, current_status=new_status, topic=body.topic)
    append_audit(case_id=cid, action_type=f"action_recorded_{body.mode}", description=f"[{body.mode.upper()} — SIMULATED] {body.proposed_action[:200]}", old_status=old_status, new_status=new_status, evidence_ids=body.policy_ids)
    add_message(cid, "assistant", f"[Plan recorded] {body.summary[:200]}")
    return {"ok": True, "old_status": old_status, "new_status": new_status}

@app.delete("/api/cases/{case_id}/conversation")
def clear_case_conversation(case_id: str):
    cid = case_id.upper().strip()
    clear_conversation(cid)
    return {"ok": True, "case_id": cid}

from fastapi.staticfiles import StaticFiles
frontend_dist = PROJECT_ROOT / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
