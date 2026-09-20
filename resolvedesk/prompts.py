"""
resolvedesk/prompts.py
----------------------
System prompt and prompt-building utilities for the Mistral agent.

Design decisions:
- The system prompt establishes the agent's identity, scope, and constraints.
  It is firm: the agent cannot grant access, send emails, or override policy rules.
- We pass the case data and policy text as context in the messages, not by
  instructing the model to "look up" data it doesn't have.
- We never include API keys, real credentials, or internal stack traces in prompts.
- The prompt explicitly forbids the model from inventing URLs, deadlines, or approvers.
"""

from datetime import date


SYSTEM_PROMPT = """You are ResolveDesk, an AI service desk assistant for Chillstack.
Your role is to help operators analyse employee IT support requests and determine the correct next step.

ASSIGNMENT CONTEXT:
- Company: Chillstack
- Exercise week: Monday 21 September 2026 through Friday 25 September 2026
- You operate within a bounded, simulated environment. All actions are explicitly simulated.

WHAT YOU MUST DO:
1. Analyse the case using the tools available to you.
2. Retrieve relevant policy text and existing case records using the provided tools.
3. Identify the topic, required approvals, missing information, and any policy conflicts.
4. Produce a structured recommendation — a plan — that cites specific policy IDs.
5. Ask targeted clarifying questions if critical information is missing.
6. Distinguish between original source facts and newly reported information.
7. CRITICAL: When you have finished your analysis, you MUST call the `stage_plan` tool to submit your final recommendation. Do not just write it in text; you must execute the tool.

WHAT YOU MUST NEVER DO:
- Never grant access, unlock accounts, send emails, install software, or ship equipment.
  All such actions are simulated only, with explicit operator confirmation.
- Never invent portal URLs, exact deadlines, approver names, catalog items, or credentials.
- Never claim that urgency, rank, or employee assertion authorises an action.
- Never present employee-typed text ("Finance approved") as verified authorisation.
- Never call yourself a new or trained AI model. You are a reasoning assistant using Mistral.
- Never claim to resolve a case just because you have generated an answer.
- Never duplicate an action or reopen a closed case.
- Never expose internal stack traces, API keys, or implementation details to the user.

TOOL-CALLING RULES:
- Use tools purposefully: retrieve what you need, then reason.
- Do not call every tool on every case — use only what is relevant.
- If a tool returns an error, report it honestly and continue with available information.
- Maximum iterations: use the fewest tool calls needed to produce a sound recommendation.

PLAN STRUCTURE:
Every recommendation must include:
- Case ID and topic
- Plain-English employee-facing explanation
- Policy IDs cited (from KB-01 through KB-10 and ASSET-Q2-2026)
- Missing information or questions for the employee
- Any policy conflicts (especially KB-03 vs ASSET-Q2-2026 for laptops)
- Proposed action and routing (e.g., IT, Security, Finance, Self-service)
- Proposed status change
- Clear statement that all actions are simulated

POLICY CONFLICT — LAPTOPS:
KB-03 states a 3-year replacement threshold.
ASSET-Q2-2026 (updated Q2 2026) states a 4-year refresh cycle.
No precedence rule is supplied. ALWAYS show both policies and route clarification
to IT and Finance/Assets. Do not declare either policy authoritative.

EXISTING CASE STATES:
Some cases already have active work (e.g., Security review pending, technician assigned).
Always preserve existing states. Do not duplicate actions or restart processes.

CLOSED TICKETS:
Closed tickets are read-only history. Do not reopen or action them.
They can be cited as context but not as authority for new approvals.

LANGUAGE:
Be clear, professional, and direct. Write in plain English that a support operator
can read aloud to an employee. Avoid technical jargon unless necessary.
"""


def build_analysis_prompt(
    case: dict,
    policies: list[dict],
    db_state: dict | None,
    clarifications: list[dict],
    conversation_history: list[dict],
) -> str:
    """
    Build the user-turn message for the Mistral agent, containing all case context.
    This is sent after the system prompt and before any tool calls.
    """
    lines = [
        f"## Case to Analyse: {case.get('id', 'Unknown')}",
        "",
        "### Source Record (immutable)",
        f"- Employee: {case.get('employee', 'Unknown')}",
        f"- Email: {case.get('email', 'Not supplied')}",
        f"- Opened: {case.get('opened', 'Not supplied')}",
        f"- Request: {case.get('request', case.get('issue_summary', 'Not supplied'))}",
        f"- Initial Action: {case.get('initial_action', case.get('source_status', 'Not supplied'))}",
        f"- Record Type: {case.get('record_type', 'request')}",
        f"- Is Closed: {case.get('is_closed', False)}",
        "",
    ]

    if db_state:
        lines += [
            "### Current Application State",
            f"- Current Status: {db_state.get('current_status', 'Not yet recorded')}",
            f"- Source Status: {db_state.get('source_status', 'N/A')}",
            f"- Version: {db_state.get('version', 1)}",
            "",
        ]

    if clarifications:
        lines += ["### Reported Clarifications (operator/employee submitted — not independently verified)"]
        for c in clarifications:
            lines.append(f"- [{c.get('submitted_at', '')}] {c.get('clarification', '')}")
            if c.get("structured_data"):
                import json
                try:
                    sd = json.loads(c["structured_data"]) if isinstance(c["structured_data"], str) else c["structured_data"]
                    lines.append(f"  Structured facts: {sd}")
                except Exception:
                    pass
        lines.append("")

    if conversation_history:
        lines += ["### Conversation History (this case only)"]
        for msg in conversation_history[-6:]:  # last 6 messages to keep context manageable
            role = msg.get("role", "?").upper()
            lines.append(f"- [{role}]: {msg.get('content', '')}")
        lines.append("")

    if policies:
        lines += ["### Relevant Policies (from source data)"]
        for p in policies:
            lines.append(f"**{p['id']} — {p['title']}**")
            lines.append(p["text"])
            if p.get("conflict_note"):
                lines.append(f"⚠️ CONFLICT NOTE: {p['conflict_note']}")
            lines.append("")

    lines += [
        "### Your Task",
        "1. Use the available tools to retrieve any additional policy or case evidence you need.",
        "2. Identify the topic, apply the relevant rules, and determine the correct next step.",
        "3. Call `stage_plan` with a complete structured plan.",
        "4. If critical information is missing, call `ask_clarification` first.",
        "5. Do not invent information that is not in the source data.",
        "6. All proposed actions are simulated — state this clearly in the plan.",
    ]

    return "\n".join(lines)


def build_offline_prompt(case: dict, policies: list[dict], clarifications: list[dict]) -> str:
    """
    Build a plain prompt for the offline rules-demo mode.
    This mode uses Python rules only — no LLM is involved.
    The output is clearly labelled as offline/demo output.
    """
    return (
        f"[OFFLINE RULES-DEMO MODE — No LLM is active]\n"
        f"Analysing case {case.get('id', '?')} using policy rules only.\n"
        f"Relevant policies: {[p['id'] for p in policies]}\n"
        f"Clarifications recorded: {len(clarifications)}"
    )
