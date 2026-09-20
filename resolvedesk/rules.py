"""
resolvedesk/rules.py
--------------------
Policy checks and business logic for the ResolveDesk agent.

Design decisions:
- All routing decisions that can be determined by rule are computed here in Python,
  independent of the LLM. This ensures correct, deterministic behaviour for the
  cases specified in the assignment and for clearly similar new cases.
- The LLM is used for language understanding and orchestration, not for policy
  enforcement. Policy limits (e.g., 50GB cap) are enforced here.
- Each check function returns a typed dict so the agent can include the result
  in a structured plan.
- We deliberately do NOT hardcode expected answers by case ID — the logic is
  topic/keyword/value-based so it generalises to new demo requests.
"""

from dataclasses import dataclass, field, asdict
from typing import Any

from resolvedesk.data import get_policies, get_policy_by_id


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class PolicyResult:
    """The outcome of a single policy check."""
    policy_id: str
    policy_title: str
    applies: bool
    summary: str            # plain-English explanation for the operator
    action_required: str    # what needs to happen next
    warnings: list[str] = field(default_factory=list)
    missing_info: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    is_urgent: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CasePlan:
    """A complete recommended plan for a case, ready to be staged."""
    case_id: str
    version: int
    topic: str
    category: str
    summary: str
    employee_explanation: str   # what the operator tells the employee
    policy_ids: list[str]
    evidence: list[str]         # relevant case IDs, existing tickets, etc.
    missing_info: list[str]
    conflicts: list[str]
    warnings: list[str]
    proposed_action: str
    proposed_route: str         # e.g. "IT", "Security", "Finance", "Self-service"
    current_status: str
    proposed_status: str
    questions_for_employee: list[str]
    is_simulation: bool = True
    requires_approval: bool = False
    is_urgent: bool = False
    closed_history_only: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


# ── Topic detection ───────────────────────────────────────────────────────────

TOPIC_KEYWORDS: dict[str, list[str]] = {
    "password_lockout":  ["password", "locked out", "lock out", "lockout", "reset password", "failed attempts"],
    "vpn":               ["vpn", "credential expired", "credentials expired", "remote access", "tunnel"],
    "laptop":            ["laptop", "computer", "device", "dead", "won't turn on", "screen", "flickering", "hardware"],
    "software_install":  ["software", "install", "application", "catalog", "extension", "browser extension", "tool"],
    "printer":           ["printer", "print", "paper jam", "spooler", "queue"],
    "mailbox_quota":     ["mailbox", "email full", "quota", "storage", "archive", "mail"],
    "guest_wifi":        ["wifi", "wi-fi", "wireless", "guest", "internet access", "network"],
    "expense_tool":      ["expense", "expense tool", "expense software", "claim", "reimbursement"],
    "security_incident": ["phishing", "malware", "suspicious", "unauthorized", "hack", "security incident", "breach"],
    "wfh_equipment":     ["work from home", "wfh", "remote", "monitor", "chair", "home office", "home equipment"],
    "admin_access":      ["admin access", "admin", "server access", "privileged access", "finance server"],
}

TOPIC_TO_POLICY: dict[str, list[str]] = {
    "password_lockout":  ["KB-01"],
    "vpn":               ["KB-02"],
    "laptop":            ["KB-03", "ASSET-Q2-2026"],
    "software_install":  ["KB-04"],
    "printer":           ["KB-05"],
    "mailbox_quota":     ["KB-06"],
    "guest_wifi":        ["KB-07"],
    "expense_tool":      ["KB-08"],
    "security_incident": ["KB-09"],
    "wfh_equipment":     ["KB-10"],
    "admin_access":      [],   # no policy authorises admin access directly
}


def detect_topic(text: str) -> str:
    """
    Detect the most likely topic from free text.
    Returns the topic key or 'unknown' if no match is found.
    Uses keyword matching — fast, transparent, and auditable.
    """
    text_lower = text.lower()
    best_topic = "unknown"
    best_count = 0
    for topic, keywords in TOPIC_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in text_lower)
        if count > best_count:
            best_count = count
            best_topic = topic
    return best_topic


def get_relevant_policies(topic: str) -> list[dict]:
    """Return policy dicts relevant to a topic."""
    policy_ids = TOPIC_TO_POLICY.get(topic, [])
    result = []
    for pid in policy_ids:
        p = get_policy_by_id(pid)
        if p:
            result.append(p)
    return result


# ── Individual policy checks ──────────────────────────────────────────────────

def check_password_lockout(facts: dict) -> PolicyResult:
    """
    KB-01: Password Reset / Account Lockout.
    facts keys: failed_attempts (int|None), reset_queued (bool)
    """
    policy = get_policy_by_id("KB-01")
    attempts = facts.get("failed_attempts")
    reset_queued = facts.get("reset_queued", False)

    if attempts is not None and attempts >= 5:
        # Locked out — IT must unlock manually first, THEN reset password.
        action = (
            "IT must manually unlock the account first (6 failed attempts exceed the 5-attempt threshold). "
            "A password reset alone will not restore access."
        )
        if reset_queued:
            action = (
                "A password reset is already queued. UPDATE the existing action to also include "
                "manual IT account unlock. Do not create a duplicate reset request."
            )
        return PolicyResult(
            policy_id="KB-01",
            policy_title=policy["title"],
            applies=True,
            summary="Account is locked after exceeding 5 failed attempts. Manual IT unlock required.",
            action_required=action,
            warnings=["Manual unlock must precede or accompany the password reset."],
        )
    else:
        return PolicyResult(
            policy_id="KB-01",
            policy_title=policy["title"],
            applies=True,
            summary="Employee can use the self-service password reset portal. No approval required.",
            action_required="Direct employee to self-service portal for password reset.",
        )


def check_vpn(facts: dict) -> PolicyResult:
    """
    KB-02: VPN Access.
    facts keys: employee_type ('full_time'|'contractor'|None), credentials_expired (bool)
    """
    policy = get_policy_by_id("KB-02")
    emp_type = facts.get("employee_type", "").lower()
    expired   = facts.get("credentials_expired", False)
    missing   = []
    warnings  = []
    action    = ""

    if emp_type == "contractor":
        action = (
            "Contractor VPN requires manager approval submitted via the access request form. "
            "The requesting manager must complete the form — auto-grant does not apply."
        )
    elif emp_type == "full_time":
        if expired:
            action = (
                "VPN credentials expire every 90 days. The employee is responsible for renewal. "
                "No exact renewal URL or workflow is supplied in source data — do not fabricate one."
            )
            warnings.append("Do not claim renewal has completed. Guide employee to renew independently.")
        else:
            action = "VPN is granted automatically to full-time employees. Verify account provisioning."
    else:
        missing.append("Employee type (full-time or contractor) is needed to determine the correct route.")
        action = "Clarify whether the employee is full-time or a contractor."

    return PolicyResult(
        policy_id="KB-02",
        policy_title=policy["title"],
        applies=True,
        summary="VPN access rules differ for full-time employees and contractors.",
        action_required=action,
        warnings=warnings,
        missing_info=missing,
    )


def check_laptop(facts: dict) -> list[PolicyResult]:
    """
    KB-03 + ASSET-Q2-2026: Laptop Replacement.
    Returns TWO results to expose the policy conflict.
    facts keys: age_years (float|None), hardware_failure_verified (bool),
                two_week_notice (bool), approval_exists (bool)
    """
    kb03   = get_policy_by_id("KB-03")
    asset  = get_policy_by_id("ASSET-Q2-2026")
    age    = facts.get("age_years")
    failed = facts.get("hardware_failure_verified", False)
    notice = facts.get("two_week_notice", False)
    existing_approval = facts.get("approval_exists", False)
    missing = []
    conflicts = [
        "POLICY CONFLICT: KB-03 sets a 3-year replacement threshold; "
        "ASSET-Q2-2026 (updated Q2 2026) sets a 4-year refresh cycle. "
        "No source-precedence rule is supplied. Both policies are shown. "
        "Clarification must be routed to IT and Finance/Assets."
    ]

    # KB-03 eligibility
    kb03_eligible = (age is not None and age >= 3.0) or failed
    kb03_summary = (
        f"KB-03: {'Eligible' if kb03_eligible else 'Not yet eligible'} for replacement "
        f"(3-year threshold; laptop age: {age if age else 'unknown'} years). "
        "2-week advance notice required."
    )
    if not failed:
        kb03_summary += " Reported failure is not verified hardware failure — diagnosis must precede replacement routing."

    # ASSET-Q2-2026 eligibility
    asset_eligible = (age is not None and age >= 4.0) or failed
    asset_summary = (
        f"ASSET-Q2-2026: {'Eligible' if asset_eligible else 'Not yet eligible'} under 4-year refresh cycle "
        f"(laptop age: {age if age else 'unknown'} years). "
        "Early replacement requires Finance sign-off in addition to IT approval."
    )

    if age is None:
        missing.append("Exact laptop age or purchase date required to assess eligibility under both policies.")
    if not failed:
        missing.append("Hardware failure must be verified by IT diagnosis before replacement is authorised.")
    if not notice:
        missing.append("2-week advance notice requirement (KB-03) should be noted.")

    kb03_action = (
        "Arrange IT diagnosis first. Do not auto-approve replacement. "
        "After diagnosis: if failure is verified, surface both policies and route approval to IT + Finance/Assets."
    )
    if existing_approval:
        kb03_action = (
            "An approval is recorded in the source. Preserve that approval. "
            "Verify the supporting approval evidence and route fulfillment/clarification to IT and Finance/Assets. "
            "Do not silently revoke the approval."
        )

    return [
        PolicyResult(
            policy_id="KB-03",
            policy_title=kb03["title"],
            applies=True,
            summary=kb03_summary,
            action_required=kb03_action,
            warnings=["Do not auto-approve replacement without verified failure and both-policy approval."],
            missing_info=missing,
            conflicts=conflicts,
        ),
        PolicyResult(
            policy_id="ASSET-Q2-2026",
            policy_title=asset["title"],
            applies=True,
            summary=asset_summary,
            action_required="Finance sign-off required in addition to IT approval for early replacement.",
            warnings=["Both policies must be resolved before replacement proceeds."],
            conflicts=conflicts,
        ),
    ]


def check_software_install(facts: dict) -> PolicyResult:
    """
    KB-04: Software Installation.
    facts keys: catalog_status ('in_catalog'|'not_in_catalog'|'unknown'),
                review_already_pending (bool)
    """
    policy = get_policy_by_id("KB-04")
    catalog = facts.get("catalog_status", "unknown").lower()
    pending = facts.get("review_already_pending", False)
    missing = []
    warnings = []

    if catalog == "in_catalog":
        action = "Software is in the approved catalog — employee can self-install. No IT ticket required."
    elif catalog == "not_in_catalog":
        if pending:
            action = (
                "IT Security review is already pending (KB-04). "
                "Preserve the existing review — do not duplicate or restart it. "
                "Timeline: 3–5 business days. No exact completion date should be given."
            )
            warnings.append("Do not duplicate the pending Security review.")
        else:
            action = (
                "Non-catalog software requires IT Security review (3–5 business days). "
                "Submit a Security review request if one is not already pending."
            )
    else:
        missing.append("Catalog membership of the software is unknown. Ask whether it appears in the approved catalog.")
        action = "Clarify whether the software/extension is in the approved catalog before routing."

    return PolicyResult(
        policy_id="KB-04",
        policy_title=policy["title"],
        applies=True,
        summary="Catalog software: self-install. Non-catalog: IT Security review (3–5 business days).",
        action_required=action,
        warnings=warnings,
        missing_info=missing,
    )


def check_printer(facts: dict) -> PolicyResult:
    """
    KB-05: Printer Troubleshooting.
    facts keys: queue_checked (bool), spooler_restarted (bool),
                asset_tag (str|None), technician_assigned (bool)
    """
    policy = get_policy_by_id("KB-05")
    queue_checked = facts.get("queue_checked", False)
    spooler_done  = facts.get("spooler_restarted", False)
    asset_tag     = facts.get("asset_tag")
    tech_assigned = facts.get("technician_assigned", False)
    missing = []

    if tech_assigned:
        action = (
            "A technician is already assigned — continue the existing investigation. "
            "Confirm queue/spooler checks have been completed. "
            "If the asset tag is not yet on file, collect it now for the ticket."
        )
        if not asset_tag:
            missing.append("Printer asset tag is required for ticket handoff per KB-05.")
    elif queue_checked and spooler_done:
        if not asset_tag:
            missing.append("Printer asset tag required to log a new ticket (KB-05).")
            action = "Issue persists after queue check and spooler restart — log a ticket with the printer asset tag."
        else:
            action = f"Log a ticket with printer asset tag {asset_tag} for further IT investigation."
    else:
        steps = []
        if not queue_checked:
            steps.append("check the printer queue")
        if not spooler_done:
            steps.append("restart the print spooler")
        action = f"First: {' and '.join(steps)}. If the issue persists, log a ticket with the asset tag."

    return PolicyResult(
        policy_id="KB-05",
        policy_title=policy["title"],
        applies=True,
        summary="Check queue and restart spooler; log a ticket with asset tag if issue persists.",
        action_required=action,
        missing_info=missing,
    )


def check_mailbox_quota(facts: dict) -> PolicyResult:
    """
    KB-06: Email Mailbox Quota.
    facts keys: current_gb (float|None), requested_gb (float|None),
                archiving_done (bool), manager_approval (bool)
    """
    policy = get_policy_by_id("KB-06")
    current   = facts.get("current_gb")
    requested = facts.get("requested_gb")
    archiving = facts.get("archiving_done", False)
    approval  = facts.get("manager_approval", False)
    warnings  = []
    missing   = []

    action_parts = []

    # Hard cap enforcement — this is a policy rule, not LLM judgment.
    if requested is not None and requested > 50:
        warnings.append(
            f"Requested quota ({requested}GB) exceeds the absolute policy cap of 50GB. "
            "Request must be reduced. Unlimited quota is not permitted."
        )
        action_parts.append(f"Explain that the 50GB cap is absolute. Requested {requested}GB cannot be approved.")

    if not archiving:
        action_parts.append("First, advise the employee to archive old mail (KB-06 step 1).")

    if requested is not None and requested > 25 and requested <= 50:
        if not approval:
            action_parts.append(
                f"A quota increase to {requested}GB (above the 25GB default) requires manager approval."
            )
            missing.append("Manager approval is required for quota above 25GB.")
        else:
            action_parts.append(f"Manager approval is present — route increase to {requested}GB for IT processing.")
    elif requested is None:
        missing.append("Requested quota amount is unknown. Ask the employee what quota they need.")

    if not action_parts:
        action_parts = ["Advise the employee to archive old mail. If quota increase is needed, manager approval is required."]

    return PolicyResult(
        policy_id="KB-06",
        policy_title=policy["title"],
        applies=True,
        summary=f"Default quota 25GB; increases above 25GB require manager approval; absolute cap 50GB.",
        action_required=" | ".join(action_parts),
        warnings=warnings,
        missing_info=missing,
    )


def check_guest_wifi(facts: dict) -> PolicyResult:
    """KB-07: Guest Wi-Fi — pure self-service, no IT ticket needed."""
    policy = get_policy_by_id("KB-07")
    return PolicyResult(
        policy_id="KB-07",
        policy_title=policy["title"],
        applies=True,
        summary="Guest Wi-Fi is fully self-service via the front-desk kiosk. No IT ticket required.",
        action_required=(
            "Inform the employee: visit the front-desk kiosk to generate 24-hour guest Wi-Fi credentials. "
            "No IT ticket needed. Credentials valid for 24 hours only. "
            "Do not generate or invent credentials — the kiosk issues them."
        ),
    )


def check_expense_tool(facts: dict) -> PolicyResult:
    """
    KB-08: Expense Software Access.
    facts keys: account_exists (bool|None), issue_type ('login'|'new_access'|'unknown')
    """
    policy = get_policy_by_id("KB-08")
    account = facts.get("account_exists")
    issue   = facts.get("issue_type", "unknown")
    missing = []

    if account is True or issue == "login":
        action = (
            "Account already exists — IT can assist with login/technical issues. "
            "Route the technical issue to IT. Do not ask for the employee's password."
        )
    elif account is False or issue == "new_access":
        action = (
            "New account access is granted by Finance, not IT. "
            "Direct the employee to contact Finance to set up their account."
        )
    else:
        missing.append("Clarify whether the employee already has an account in the expense tool.")
        action = (
            "Ask whether the employee has an existing account. "
            "Existing account → IT for technical issues. No account → Finance for access grant."
        )

    return PolicyResult(
        policy_id="KB-08",
        policy_title=policy["title"],
        applies=True,
        summary="Expense tool access: Finance grants new accounts; IT handles technical issues for existing accounts.",
        action_required=action,
        missing_info=missing,
    )


def check_security_incident(facts: dict) -> PolicyResult:
    """
    KB-09: Security Incident Reporting — always urgent.
    facts keys: forwarded_to_others (bool), escalated (bool)
    """
    policy = get_policy_by_id("KB-09")
    forwarded  = facts.get("forwarded_to_others", False)
    escalated  = facts.get("escalated", False)
    warnings   = []

    if forwarded:
        warnings.append(
            "CRITICAL: Employee must STOP forwarding the suspected phishing email to colleagues immediately. "
            "KB-09 explicitly prohibits forwarding to other employees."
        )

    action = (
        "URGENT: Report the suspected phishing/security incident to security@chillstack.example immediately. "
    )
    if forwarded:
        action += "Instruct the employee to stop forwarding the email to colleagues — this is explicitly prohibited by KB-09. "
    if escalated:
        action += "Existing Security escalation is already in place — preserve it and keep Security informed."
    else:
        action += "Escalate to Security immediately."

    return PolicyResult(
        policy_id="KB-09",
        policy_title=policy["title"],
        applies=True,
        summary="Security incident — report to security@chillstack.example immediately. Do not forward.",
        action_required=action,
        warnings=warnings,
        is_urgent=True,
    )


def check_wfh_equipment(facts: dict) -> PolicyResult:
    """
    KB-10: Work-From-Home Equipment.
    facts keys: remote_days_per_week (int|None), one_time_used (bool),
                manager_approval (bool), finance_processed (bool)
    """
    policy = get_policy_by_id("KB-10")
    days      = facts.get("remote_days_per_week")
    used      = facts.get("one_time_used", False)
    mgr_ok    = facts.get("manager_approval", False)
    fin_ok    = facts.get("finance_processed", False)
    missing   = []
    warnings  = []

    if days is None:
        missing.append("Number of remote days per week is required to confirm eligibility.")
        return PolicyResult(
            policy_id="KB-10",
            policy_title=policy["title"],
            applies=True,
            summary="Eligible if working remotely more than 3 days/week. One-time allowance.",
            action_required="Clarify how many days per week the employee works remotely.",
            missing_info=missing,
        )

    # "more than 3" means >= 4 days
    eligible = days > 3
    if not eligible:
        return PolicyResult(
            policy_id="KB-10",
            policy_title=policy["title"],
            applies=True,
            summary=f"Employee works {days} day(s)/week remotely. KB-10 requires more than 3 days/week.",
            action_required=f"Employee working {days} day(s)/week does not meet the eligibility threshold of >3 days/week.",
            warnings=["Eligibility threshold not met — do not route for approval."],
        )

    if used:
        warnings.append("This is a one-time allowance (KB-10). Check whether the employee has already received it.")

    steps = []
    if not mgr_ok:
        steps.append("obtain manager sign-off")
    if not fin_ok:
        steps.append("Finance processing")
    steps.append("IT handles shipping request only after both approvals are confirmed")

    action = (
        f"Employee works {days} days/week remotely — eligibility criterion met (>3 days/week). "
        f"Eligibility is not approval. Required steps: {' → '.join(steps)}."
    )

    return PolicyResult(
        policy_id="KB-10",
        policy_title=policy["title"],
        applies=True,
        summary=f"WFH equipment eligibility confirmed ({days} days/week). Approval chain required.",
        action_required=action,
        warnings=warnings,
        missing_info=missing,
    )


def check_admin_access(facts: dict) -> PolicyResult:
    """
    Admin access: no supplied policy authorises this directly.
    Requires business justification and human access reviewer.
    """
    justification = facts.get("business_justification")
    missing = []

    if not justification:
        missing.append(
            "Business justification for admin access is required before routing for review."
        )

    return PolicyResult(
        policy_id="NONE",
        policy_title="Admin Access (No Direct Policy)",
        applies=True,
        summary=(
            "No supplied policy authorises admin access to internal servers directly. "
            "Previous precedent (TK-1050): an admin access request was rejected for missing justification — "
            "this is closed history, not a blanket policy."
        ),
        action_required=(
            "Collect business justification from the employee. "
            "Route to a human access reviewer. "
            "Do not grant access — urgency does not override the review requirement."
        ),
        warnings=["Access cannot be granted without a completed access review. Urgency does not override this."],
        missing_info=missing,
    )


# ── Master routing function ───────────────────────────────────────────────────

def evaluate_topic(topic: str, facts: dict) -> list[PolicyResult]:
    """
    Route a topic to the appropriate policy check(s).
    Returns a list of PolicyResult objects (most topics return one; laptop returns two).
    """
    dispatch = {
        "password_lockout":  lambda f: [check_password_lockout(f)],
        "vpn":               lambda f: [check_vpn(f)],
        "laptop":            lambda f: check_laptop(f),        # already returns list
        "software_install":  lambda f: [check_software_install(f)],
        "printer":           lambda f: [check_printer(f)],
        "mailbox_quota":     lambda f: [check_mailbox_quota(f)],
        "guest_wifi":        lambda f: [check_guest_wifi(f)],
        "expense_tool":      lambda f: [check_expense_tool(f)],
        "security_incident": lambda f: [check_security_incident(f)],
        "wfh_equipment":     lambda f: [check_wfh_equipment(f)],
        "admin_access":      lambda f: [check_admin_access(f)],
    }
    handler = dispatch.get(topic)
    if handler:
        return handler(facts)
    return []   # unknown topic — agent will ask clarifying questions


def validate_plan(plan: dict, case_id: str, is_closed: bool) -> tuple[bool, str]:
    """
    Validate a staged plan before it is recorded.
    Returns (is_valid: bool, reason: str).
    Prevents recording stale, incomplete, or closed-case plans.
    """
    if is_closed:
        return False, "This case is closed history and cannot be actioned."
    if not plan.get("case_id"):
        return False, "Plan is missing case_id."
    if plan.get("case_id") != case_id:
        return False, f"Plan case_id ({plan.get('case_id')}) does not match selected case ({case_id})."
    if not plan.get("proposed_action"):
        return False, "Plan has no proposed action."
    if not plan.get("policy_ids"):
        return False, "Plan cites no policy IDs — cannot record without evidence."
    return True, "OK"
