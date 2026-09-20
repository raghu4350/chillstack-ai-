"""
resolvedesk/tools.py
--------------------
Tool schemas (for Mistral function-calling) and guarded execution functions.

Design decisions:
- Each tool has a JSON schema that Mistral uses to decide when and how to call it.
- The execution functions are pure Python — no eval(), no shell commands, no
  arbitrary file access or SQL injection risks.
- The model proposes tool calls; this module validates and executes them safely.
- Tool arguments are validated before execution; invalid arguments return an error
  message rather than raising an exception that could surface in the UI.
- `record_local_action` is a special tool that requires explicit operator confirmation
  in the UI before it runs. The model can stage a plan but cannot bypass the review.
"""

import json
from typing import Any

from resolvedesk.data import (
    get_policy_by_id,
    get_request_by_id,
    get_ticket_by_id,
    get_policies_for_topic,
    get_requests,
    get_tickets,
)
from resolvedesk.database import (
    get_case_state,
    get_clarifications,
    get_audit_log,
    stage_plan as db_stage_plan,
    add_clarification,
    DB_PATH,
)
from resolvedesk.rules import evaluate_topic, detect_topic
from pathlib import Path


# ── Tool schemas (Mistral function-calling format) ────────────────────────────

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_case",
            "description": (
                "Retrieve the full source record for a case (employee request or ticket), "
                "its current application state, and any recorded clarifications. "
                "Use this first to understand the case before applying rules."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id": {
                        "type": "string",
                        "description": "The case ID, e.g. 'REQ-01' or 'TK-1043'.",
                    }
                },
                "required": ["case_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_policy",
            "description": (
                "Retrieve the exact text and metadata of a policy by its ID. "
                "Valid IDs: KB-01 through KB-10, ASSET-Q2-2026. "
                "Use this to cite exact policy text in a plan."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "policy_id": {
                        "type": "string",
                        "description": "The policy ID, e.g. 'KB-01' or 'ASSET-Q2-2026'.",
                    }
                },
                "required": ["policy_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_related_history",
            "description": (
                "Search for related tickets or requests by topic keyword. "
                "Returns a list of records with matching topics, marked as context only — "
                "not as authority. Do not assume identity matches between records."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Topic keyword to search for, e.g. 'vpn', 'laptop', 'phishing'.",
                    }
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "evaluate_case",
            "description": (
                "Apply business rules to a case and return a typed policy evaluation. "
                "Provide known facts as structured fields. "
                "Returns policy results including required actions, missing information, and conflicts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id": {
                        "type": "string",
                        "description": "The case ID being evaluated.",
                    },
                    "topic": {
                        "type": "string",
                        "description": (
                            "The detected topic: password_lockout, vpn, laptop, software_install, "
                            "printer, mailbox_quota, guest_wifi, expense_tool, "
                            "security_incident, wfh_equipment, admin_access, or unknown."
                        ),
                    },
                    "facts": {
                        "type": "object",
                        "description": (
                            "Known facts for the policy check. Examples by topic: "
                            "password_lockout: {failed_attempts: 6, reset_queued: true}; "
                            "vpn: {employee_type: 'contractor', credentials_expired: false}; "
                            "laptop: {age_years: 3.5, hardware_failure_verified: false}; "
                            "mailbox_quota: {current_gb: 25, requested_gb: 35}; "
                            "wfh_equipment: {remote_days_per_week: 4}; "
                            "software_install: {catalog_status: 'not_in_catalog', review_already_pending: true}."
                        ),
                    },
                },
                "required": ["case_id", "topic", "facts"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_clarification",
            "description": (
                "Stage a clarifying question for the operator/employee when required "
                "information is missing. Use when you cannot produce a sound recommendation "
                "without additional facts. Do not ask for passwords."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id": {
                        "type": "string",
                        "description": "The case ID.",
                    },
                    "question": {
                        "type": "string",
                        "description": "The specific question to ask.",
                    },
                    "fields_needed": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of structured fields that would answer the question.",
                    },
                },
                "required": ["case_id", "question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stage_plan",
            "description": (
                "Stage a complete, structured recommendation plan for operator review. "
                "The plan is NOT executed until the operator explicitly confirms. "
                "Include all required fields."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id":               {"type": "string"},
                    "topic":                 {"type": "string"},
                    "category":              {"type": "string", "description": "e.g. 'IT', 'Security', 'Finance', 'Self-service'"},
                    "summary":               {"type": "string", "description": "Brief summary for the operator."},
                    "employee_explanation":  {"type": "string", "description": "Plain-English message for the employee."},
                    "policy_ids":            {"type": "array", "items": {"type": "string"}},
                    "evidence":              {"type": "array", "items": {"type": "string"}, "description": "Relevant case IDs or records cited."},
                    "missing_info":          {"type": "array", "items": {"type": "string"}},
                    "conflicts":             {"type": "array", "items": {"type": "string"}},
                    "warnings":              {"type": "array", "items": {"type": "string"}},
                    "proposed_action":       {"type": "string"},
                    "proposed_route":        {"type": "string"},
                    "current_status":        {"type": "string"},
                    "proposed_status":       {"type": "string"},
                    "questions_for_employee":{"type": "array", "items": {"type": "string"}},
                    "requires_approval":     {"type": "boolean"},
                    "is_urgent":             {"type": "boolean"},
                },
                "required": [
                    "case_id", "topic", "summary", "employee_explanation",
                    "policy_ids", "proposed_action", "proposed_route",
                    "current_status", "proposed_status",
                ],
            },
        },
    },
]


# ── Tool execution ────────────────────────────────────────────────────────────

def execute_tool(
    tool_name: str,
    arguments: dict,
    db_path: Path = DB_PATH,
) -> dict:
    """
    Dispatch a tool call from the Mistral agent to the appropriate Python function.
    Returns a dict with 'ok' (bool) and either 'result' or 'error'.
    All execution is guarded — no eval, no shell, no arbitrary SQL.
    """
    # Reject unsupported tool names immediately.
    supported = {t["function"]["name"] for t in TOOL_SCHEMAS}
    if tool_name not in supported:
        return {
            "ok": False,
            "error": f"Unknown tool '{tool_name}'. Supported tools: {sorted(supported)}",
        }

    try:
        if tool_name == "get_case":
            return _tool_get_case(arguments, db_path)
        elif tool_name == "get_policy":
            return _tool_get_policy(arguments)
        elif tool_name == "get_related_history":
            return _tool_get_related_history(arguments)
        elif tool_name == "evaluate_case":
            return _tool_evaluate_case(arguments)
        elif tool_name == "ask_clarification":
            return _tool_ask_clarification(arguments, db_path)
        elif tool_name == "stage_plan":
            return _tool_stage_plan(arguments, db_path)
        else:
            return {"ok": False, "error": f"Tool '{tool_name}' is defined but has no handler."}
    except KeyError as e:
        return {"ok": False, "error": f"Missing required argument: {e}"}
    except Exception as e:
        # Never expose a raw stack trace — return a sanitised error message.
        return {"ok": False, "error": f"Tool execution error in '{tool_name}': {type(e).__name__}: {e}"}


def _tool_get_case(args: dict, db_path: Path) -> dict:
    case_id = str(args.get("case_id", "")).upper().strip()
    if not case_id:
        return {"ok": False, "error": "case_id is required."}

    # Check requests first, then tickets.
    record = get_request_by_id(case_id) or get_ticket_by_id(case_id)
    if not record:
        return {"ok": False, "error": f"No source record found for case_id '{case_id}'."}

    db_state = get_case_state(case_id, db_path=db_path)
    clarifications = get_clarifications(case_id, db_path=db_path)

    return {
        "ok": True,
        "result": {
            "source_record": record,
            "application_state": db_state,
            "clarifications": clarifications,
            "clarification_count": len(clarifications),
            "is_closed": record.get("is_closed", False),
            "record_type": record.get("record_type", "request"),
        },
    }


def _tool_get_policy(args: dict) -> dict:
    policy_id = str(args.get("policy_id", "")).upper().strip()
    if not policy_id:
        return {"ok": False, "error": "policy_id is required."}

    policy = get_policy_by_id(policy_id)
    if not policy:
        valid_ids = [p["id"] for p in __import__("resolvedesk.data", fromlist=["get_policies"]).get_policies()]
        return {
            "ok": False,
            "error": f"Policy '{policy_id}' not found. Valid IDs: {valid_ids}",
        }
    return {"ok": True, "result": policy}


def _tool_get_related_history(args: dict) -> dict:
    topic = str(args.get("topic", "")).lower().strip()
    if not topic:
        return {"ok": False, "error": "topic is required."}

    matches = []
    for r in get_requests():
        if topic in r.get("topic", "").lower() or any(
            topic in kw.lower() for kw in r.get("request", "").lower().split()
        ):
            matches.append({
                "id": r["id"],
                "type": "request",
                "employee": r.get("employee"),
                "summary": r.get("request", "")[:120],
                "status": r.get("initial_action"),
                "is_closed": False,
                "context_note": "Source employee request — identity not assumed to match any ticket.",
            })
    for t in get_tickets():
        if topic in t.get("topic", "").lower():
            matches.append({
                "id": t["id"],
                "type": "ticket",
                "employee": t.get("employee"),
                "summary": t.get("issue_summary", ""),
                "status": t.get("source_status"),
                "is_closed": t.get("is_closed", False),
                "context_note": "Existing ticket — closed records are read-only history.",
            })

    return {
        "ok": True,
        "result": {
            "topic": topic,
            "matches": matches,
            "count": len(matches),
            "note": "These records are provided as context only. Do not assume identity matches.",
        },
    }


def _tool_evaluate_case(args: dict) -> dict:
    case_id = str(args.get("case_id", "")).upper().strip()
    topic   = str(args.get("topic", "unknown")).lower().strip()
    facts   = args.get("facts", {})

    if not isinstance(facts, dict):
        return {"ok": False, "error": "facts must be an object/dict."}

    results = evaluate_topic(topic, facts)
    if not results:
        return {
            "ok": True,
            "result": {
                "case_id": case_id,
                "topic": topic,
                "policy_results": [],
                "note": f"No policy rules matched topic '{topic}'. Ask clarifying questions.",
            },
        }

    return {
        "ok": True,
        "result": {
            "case_id": case_id,
            "topic": topic,
            "policy_results": [r.to_dict() for r in results],
        },
    }


def _tool_ask_clarification(args: dict, db_path: Path) -> dict:
    case_id  = str(args.get("case_id", "")).upper().strip()
    question = str(args.get("question", "")).strip()
    fields   = args.get("fields_needed", [])

    if not case_id or not question:
        return {"ok": False, "error": "case_id and question are required."}

    # Refuse to ask for passwords — safety rule.
    if "password" in question.lower():
        return {
            "ok": False,
            "error": "Questions must not ask for passwords. Ask about account existence, error messages, or workflow steps instead.",
        }

    structured = {"fields_needed": fields} if fields else None
    row_id = add_clarification(
        case_id=case_id,
        clarification=f"[AGENT QUESTION] {question}",
        structured_data=structured,
        reported_by="agent",
        db_path=db_path,
    )

    return {
        "ok": True,
        "result": {
            "case_id": case_id,
            "question_stored": question,
            "clarification_id": row_id,
            "note": "Question has been staged. Operator must present this to the employee and record the response.",
        },
    }


def _tool_stage_plan(args: dict, db_path: Path) -> dict:
    case_id = str(args.get("case_id", "")).upper().strip()
    if not case_id:
        return {"ok": False, "error": "case_id is required in the plan."}

    required_fields = ["topic", "summary", "employee_explanation", "policy_ids",
                       "proposed_action", "proposed_route", "current_status", "proposed_status"]
    missing = [f for f in required_fields if not args.get(f)]
    if missing:
        return {"ok": False, "error": f"Plan is missing required fields: {missing}"}

    plan = {
        "case_id":               case_id,
        "topic":                 args.get("topic", "unknown"),
        "category":              args.get("category", "IT"),
        "summary":               args.get("summary", ""),
        "employee_explanation":  args.get("employee_explanation", ""),
        "policy_ids":            args.get("policy_ids", []),
        "evidence":              args.get("evidence", []),
        "missing_info":          args.get("missing_info", []),
        "conflicts":             args.get("conflicts", []),
        "warnings":              args.get("warnings", []),
        "proposed_action":       args.get("proposed_action", ""),
        "proposed_route":        args.get("proposed_route", ""),
        "current_status":        args.get("current_status", ""),
        "proposed_status":       args.get("proposed_status", ""),
        "questions_for_employee":args.get("questions_for_employee", []),
        "requires_approval":     args.get("requires_approval", False),
        "is_urgent":             args.get("is_urgent", False),
        "is_simulation":         True,   # always True in this app
    }

    plan_id = db_stage_plan(case_id=case_id, plan=plan, db_path=db_path)

    return {
        "ok": True,
        "result": {
            "plan_id": plan_id,
            "case_id": case_id,
            "status": "pending",
            "note": "Plan staged for operator review. Operator must explicitly confirm to record it.",
        },
    }


# ── Offline rules-only analysis ───────────────────────────────────────────────

def run_offline_analysis(case: dict, clarifications: list[dict]) -> dict:
    """
    Generate a plan using Python rules only — no LLM required.
    Used in offline/demo mode. Clearly labelled as offline output.

    This is NOT a fallback that silently pretends to use Mistral.
    """
    topic = case.get("topic", "unknown")
    case_id = case.get("id", "?")
    is_closed = case.get("is_closed", False)

    # Extract any structured facts from clarifications.
    facts = {}
    for c in clarifications:
        if c.get("structured_data"):
            try:
                sd = json.loads(c["structured_data"]) if isinstance(c["structured_data"], str) else c["structured_data"]
                facts.update(sd)
            except (json.JSONDecodeError, TypeError):
                pass

    # Seed facts from what we know about the case.
    _seed_facts_from_case(case, facts)

    results = evaluate_topic(topic, facts)
    is_urgent = any(r.is_urgent for r in results)

    # Assemble a plan from the rules output.
    policy_ids = [r.policy_id for r in results if r.policy_id != "NONE"]
    action_parts = [r.action_required for r in results if r.action_required]
    warnings = [w for r in results for w in r.warnings]
    conflicts = [c for r in results for c in r.conflicts]
    missing   = [m for r in results for m in r.missing_info]
    questions = []

    if topic == "unknown" or not results:
        questions = [
            "Which device or application is affected?",
            "What is the error message or symptom?",
            "When did this issue start?",
        ]
        employee_explanation = (
            "I need a little more information to help you. "
            "Could you please describe: (1) which device or application isn't working, "
            "(2) what error or symptom you're seeing, and (3) when it started?"
        )
        proposed_action = "Collect more information before routing."
        proposed_route  = "Pending clarification"
        proposed_status = "Awaiting more details"
    else:
        employee_explanation = " ".join(action_parts) if action_parts else "Please see the proposed action below."
        proposed_action = action_parts[0] if action_parts else "Review required."
        proposed_route  = _get_route(topic, results)
        proposed_status = _get_proposed_status(case, results, topic)

    current_status = (
        case.get("initial_action") or case.get("source_status") or "Not started"
    )

    plan = {
        "case_id":               case_id,
        "version":               1,
        "topic":                 topic,
        "category":              _get_category(topic),
        "summary":               f"[OFFLINE RULES-DEMO] Analysis of {case_id} — {topic}",
        "employee_explanation":  employee_explanation,
        "policy_ids":            policy_ids,
        "evidence":              [],
        "missing_info":          missing,
        "conflicts":             conflicts,
        "warnings":              warnings,
        "proposed_action":       proposed_action,
        "proposed_route":        proposed_route,
        "current_status":        current_status,
        "proposed_status":       proposed_status,
        "questions_for_employee":questions,
        "requires_approval":     _requires_approval(topic, facts),
        "is_urgent":             is_urgent,
        "is_simulation":         True,
        "is_closed":             is_closed,
        "offline_mode":          True,
        "policy_results":        [r.to_dict() for r in results],
    }
    return plan


def _seed_facts_from_case(case: dict, facts: dict) -> None:
    """Populate facts dict from the source case record where values are explicit."""
    request_text = (case.get("request") or case.get("issue_summary") or "").lower()
    initial = (case.get("initial_action") or case.get("source_status") or "").lower()

    # Password/lockout
    if "6 times" in request_text or "locked out" in request_text:
        facts.setdefault("failed_attempts", 6)
    if "reset queued" in initial:
        facts.setdefault("reset_queued", True)

    # VPN
    if "credentials expired" in request_text or "expired" in request_text:
        facts.setdefault("credentials_expired", True)
    if "contractor" in request_text:
        facts.setdefault("employee_type", "contractor")

    # Printer
    if "technician assigned" in initial:
        facts.setdefault("technician_assigned", True)

    # Security
    if "forwarding" in request_text or "forward" in request_text:
        facts.setdefault("forwarded_to_others", True)
    if "escalated to security" in initial:
        facts.setdefault("escalated", True)

    # Software
    if "security review" in initial:
        facts.setdefault("review_already_pending", True)
    if "not in the software catalog" in request_text or "not in" in request_text:
        facts.setdefault("catalog_status", "not_in_catalog")

    # WFH
    if "4 days" in request_text or "four days" in request_text:
        facts.setdefault("remote_days_per_week", 4)

    # Laptop age
    import re
    age_match = re.search(r"(\d+(?:\.\d+)?)\s*years?", request_text)
    if age_match:
        facts.setdefault("age_years", float(age_match.group(1)))

    # Existing approval (for active tickets)
    if "approved" in initial and "pending fulfillment" in initial:
        facts.setdefault("approval_exists", True)


def _get_route(topic: str, results: list) -> str:
    route_map = {
        "password_lockout":  "IT",
        "vpn":               "IT / Manager (if contractor)",
        "laptop":            "IT (diagnosis) → IT + Finance/Assets (if replacement)",
        "software_install":  "IT Security",
        "printer":           "IT",
        "mailbox_quota":     "IT (after manager approval)",
        "guest_wifi":        "Self-service (front-desk kiosk)",
        "expense_tool":      "Finance (new access) or IT (technical issue)",
        "security_incident": "Security — URGENT",
        "wfh_equipment":     "Manager → Finance → IT (shipping)",
        "admin_access":      "Human Access Reviewer",
    }
    return route_map.get(topic, "IT")


def _get_category(topic: str) -> str:
    category_map = {
        "guest_wifi":        "Self-service",
        "security_incident": "Security",
        "expense_tool":      "Finance / IT",
        "wfh_equipment":     "Finance / IT",
        "admin_access":      "Access Review",
    }
    return category_map.get(topic, "IT")


def _get_proposed_status(case: dict, results: list, topic: str) -> str:
    current = (case.get("initial_action") or case.get("source_status") or "Not started").lower()
    is_urgent = any(r.is_urgent for r in results)
    has_missing = any(r.missing_info for r in results)

    if is_urgent:
        return "Escalated to Security"
    if has_missing:
        return "Awaiting clarification"
    if "not started" in current:
        return "In progress"
    return "In progress — updated"


def _requires_approval(topic: str, facts: dict) -> bool:
    approval_topics = {"laptop", "wfh_equipment", "mailbox_quota", "admin_access"}
    if topic == "vpn" and facts.get("employee_type") == "contractor":
        return True
    return topic in approval_topics
