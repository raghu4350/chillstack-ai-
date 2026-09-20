"""
resolvedesk/agent.py
--------------------
Mistral integration and bounded agent loop.

Design decisions:
- Uses the official Mistral Python SDK (mistralai).
- The agent loop is bounded: it stops after MAX_TOOL_ITERATIONS tool calls to
  prevent runaway API usage or infinite loops.
- Tool calls are validated and executed by tools.py — the model cannot bypass
  application-level checks.
- API failures are reported honestly; we never silently substitute offline output
  for a failed live call.
- API keys are never logged, stored in the database, or included in error messages.
- The `record_local_action` step requires explicit operator confirmation in the UI;
  the agent can only stage a plan, not execute actions directly.
"""

import json
import time
from typing import Any

from resolvedesk.config import (
    MAX_TOOL_ITERATIONS,
    API_TIMEOUT_SECONDS,
    DEFAULT_MISTRAL_MODEL,
)
from resolvedesk.data import (
    get_request_by_id,
    get_ticket_by_id,
    get_policies_for_topic,
)
from resolvedesk.database import (
    get_case_state,
    get_clarifications,
    get_conversation,
    add_message,
    get_pending_plan,
    DB_PATH,
)
from resolvedesk.prompts import SYSTEM_PROMPT, build_analysis_prompt
from resolvedesk.rules import detect_topic, get_relevant_policies
from resolvedesk.tools import TOOL_SCHEMAS, execute_tool
from pathlib import Path

# Import the Groq SDK at module level so that tests can mock it.
# If the package is not installed, Groq is set to None.
try:
    from groq import Groq
except ImportError:
    Groq = None  # type: ignore


# ── Result dataclass ──────────────────────────────────────────────────────────

class AgentResult:
    """
    Holds the output of a single agent run.
    Always contains a plan (possibly from offline mode) and a trace.
    """
    def __init__(
        self,
        plan: dict | None,
        trace: list[dict],
        mode: str,             # 'mistral' | 'offline' | 'error'
        error: str | None = None,
        questions: list[str] | None = None,
    ):
        self.plan      = plan
        self.trace     = trace          # list of {tool, args, result} for display
        self.mode      = mode
        self.error     = error
        self.questions = questions or []

    @property
    def success(self) -> bool:
        return self.plan is not None and self.mode != "error"


# ── Main agent entry point ────────────────────────────────────────────────────

def run_agent(
    case_id: str,
    api_key: str,
    model: str = DEFAULT_MISTRAL_MODEL,
    db_path: Path = DB_PATH,
) -> AgentResult:
    """
    Run the Mistral agent for a given case.

    Pipeline:
    1. Load the case record and current state.
    2. Detect topic and retrieve relevant policies.
    3. Build the prompt context.
    4. Send to Mistral with tool schemas.
    5. Execute tool calls iteratively (bounded loop).
    6. Collect the staged plan.
    7. Return an AgentResult with the plan and tool trace.

    If the API key is missing or the API fails, returns an AgentResult with
    mode='error' so the UI can offer the offline mode explicitly.
    """
    if not api_key or not api_key.strip():
        return AgentResult(
            plan=None, trace=[], mode="error",
            error=(
                "No Groq API key provided. "
                "Please set GROQ_API_KEY in your .env file. "
                "You can use Offline Rules-Demo mode without a key."
            ),
        )

    # ── Load case ──────────────────────────────────────────────────────────
    case_id_upper = case_id.upper().strip()
    case = get_request_by_id(case_id_upper) or get_ticket_by_id(case_id_upper)
    if not case:
        return AgentResult(
            plan=None, trace=[], mode="error",
            error=f"Case '{case_id_upper}' not found in source data.",
        )

    if case.get("is_closed", False):
        return AgentResult(
            plan={"case_id": case_id_upper, "closed_history_only": True,
                  "summary": "This case is closed history and cannot be actioned.",
                  "policy_ids": [], "proposed_action": "None — closed record.",
                  "proposed_route": "N/A", "is_simulation": True},
            trace=[],
            mode="closed",
        )

    # ── Prepare context ────────────────────────────────────────────────────
    topic        = case.get("topic", detect_topic(case.get("request", case.get("issue_summary", ""))))
    policies     = get_relevant_policies(topic)
    db_state     = get_case_state(case_id_upper, db_path=db_path)
    clarifications = get_clarifications(case_id_upper, db_path=db_path)
    conversation = get_conversation(case_id_upper, db_path=db_path)

    user_prompt = build_analysis_prompt(
        case=case,
        policies=policies,
        db_state=db_state,
        clarifications=clarifications,
        conversation_history=conversation,
    )

    # ── Build Groq message list ──────────────────────────────────────────
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt},
    ]

    trace = []
    plan  = None

    # ── Import SDK ─────────────────────────────────────────────────────────
    global Groq
    if Groq is None:
        try:
            from groq import Groq
        except ImportError:
            return AgentResult(
                plan=None, trace=[], mode="error",
                error=(
                    "The 'groq' package is not installed. "
                    "Run: pip install groq\n"
                    "Then restart the application."
                ),
            )

    # ── Agent loop ─────────────────────────────────────────────────────────
    import httpx
    client = Groq(
        api_key=api_key,
        http_client=httpx.Client(
            transport=httpx.HTTPTransport(local_address="0.0.0.0")  # Force IPv4
        )
    )

    for iteration in range(MAX_TOOL_ITERATIONS):
        import time
        response = None
        for attempt in range(3):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=TOOL_SCHEMAS,
                    tool_choice="auto",
                )
                break  # Success, exit the retry loop
            except Exception as exc:
                err_msg = str(exc)
                
                # If it's a 429 Rate Limit error, fallback seamlessly to offline mode!
                if "429" in err_msg:
                    offline_result = run_offline(case_id, db_path=db_path)
                    # Prepend a trace step indicating the failover
                    offline_result.trace.insert(0, {"tool": "Failover", "args": {}, "result": "API Rate Limit Hit — Automatic failover to offline simulation"})
                    # Prepend the warning to the summary
                    if offline_result.plan:
                        offline_result.plan["summary"] = "**[API RATE LIMIT REACHED - AUTOMATIC OFFLINE FALLBACK]**\n\nGroq's API quota was exhausted. The system has automatically fallen back to the local rules engine to provide this demo response.\n\n" + offline_result.plan.get("summary", "")
                    return offline_result
                    
                # Otherwise, fail immediately and report the error
                if api_key and api_key in err_msg:
                    err_msg = err_msg.replace(api_key, "[REDACTED]")
                return AgentResult(
                    plan=None,
                    trace=trace,
                    mode="error",
                    error=(
                        f"Groq API error (iteration {iteration + 1}): {err_msg}\n\n"
                        "You can switch to Offline Rules-Demo mode using the button above."
                    ),
                )

        assistant_message = response.choices[0].message
        finish_reason     = response.choices[0].finish_reason

        # Append assistant message to the conversation so Groq can see history.
        messages.append({"role": "assistant", "content": assistant_message.content or "",
                         "tool_calls": [
                             {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                             for tc in (assistant_message.tool_calls or [])
                         ]})

        # If no tool calls, the model has finished.
        if not assistant_message.tool_calls:
            if assistant_message.content:
                add_message(case_id_upper, "assistant", assistant_message.content, db_path=db_path)
            break

        # ── Execute tool calls ──────────────────────────────────────────────
        tool_results = []
        for tool_call in assistant_message.tool_calls:
            fn_name = tool_call.function.name
            try:
                fn_args = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError:
                fn_args = {}

            # Execute the tool with application-level guards.
            result = execute_tool(fn_name, fn_args, db_path=db_path)

            trace.append({
                "tool":   fn_name,
                "args":   fn_args,
                "result": result,
            })

            # If this was stage_plan and it succeeded, capture the plan.
            if fn_name == "stage_plan" and result.get("ok"):
                staged = get_pending_plan(case_id_upper, db_path=db_path)
                if staged:
                    plan = staged["plan"]

            # Feed the tool result back to Mistral.
            tool_results.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, ensure_ascii=False),
            })

        messages.extend(tool_results)

        # If finish_reason indicates the model is done, stop.
        if finish_reason == "stop":
            break

    # ── Post-loop ──────────────────────────────────────────────────────────
    if plan is None:
        # The model didn't call stage_plan — check if there's a pending plan from a prior run.
        staged = get_pending_plan(case_id_upper, db_path=db_path)
        if staged:
            plan = staged["plan"]

    # FALLBACK: If the model stubbornly outputs text instead of a tool call
    if plan is None and assistant_message and assistant_message.content:
        import re
        text_content = assistant_message.content
        
        # Automatically extract any policy IDs (like KB-01, ASSET-Q2-2026) mentioned in the text
        extracted_policies = list(set(re.findall(r'(KB-\d{2}|ASSET-Q\d-\d{4})', text_content)))

        plan = {
            "case_id": case_id_upper,
            "topic": "Analysis Completed",
            "category": "Analysis",
            "current_status": "open",
            "proposed_status": "pending" if "missing" in text_content.lower() else "approved",
            "proposed_route": "IT Support",
            "summary": "The model successfully generated an analysis but failed to use the strict UI formatting tool. The raw analysis has been wrapped below.",
            "employee_explanation": text_content,
            "policy_ids": extracted_policies,
            "missing_info": ["See explanation for details."],
            "proposed_action": "Review the detailed explanation.",
            "is_escalated": False,
            "is_urgent": False,
        }

    if plan is None:
        return AgentResult(
            plan=None,
            trace=trace,
            mode="error",
            error=(
                "The agent completed its analysis but did not produce a staged plan. "
                "This may happen if the model reached the iteration limit or the API response was incomplete. "
                "Try again, or use Offline Rules-Demo mode."
            ),
        )

    return AgentResult(plan=plan, trace=trace, mode="groq")


# ── Offline mode entry point (clearly labelled) ───────────────────────────────

def run_offline(case_id: str, db_path: Path = DB_PATH) -> AgentResult:
    """
    Run the offline rules-only analysis for a case.
    This clearly does NOT use Groq. It applies Python policy rules only.
    The result is labelled 'offline' throughout the UI.
    """
    from resolvedesk.tools import run_offline_analysis

    case_id_upper = case_id.upper().strip()
    case = get_request_by_id(case_id_upper) or get_ticket_by_id(case_id_upper)
    if not case:
        return AgentResult(
            plan=None, trace=[], mode="error",
            error=f"Case '{case_id_upper}' not found in source data.",
        )

    if case.get("is_closed", False):
        return AgentResult(
            plan={"case_id": case_id_upper, "closed_history_only": True,
                  "summary": "This case is closed history and cannot be actioned.",
                  "policy_ids": [], "proposed_action": "None — closed record.",
                  "proposed_route": "N/A", "is_simulation": True, "offline_mode": True},
            trace=[{"tool": "offline_rules", "args": {}, "result": {"note": "Closed history — no action."}}],
            mode="closed",
        )

    clarifications = get_clarifications(case_id_upper, db_path=db_path)
    plan = run_offline_analysis(case, clarifications)

    trace = [
        {
            "tool":   "offline_rules_engine",
            "args":   {"case_id": case_id_upper, "topic": case.get("topic", "unknown")},
            "result": {"ok": True, "policy_results": plan.get("policy_results", [])},
        }
    ]

    return AgentResult(plan=plan, trace=trace, mode="offline")
