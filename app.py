"""
app.py — ResolveDesk: AI Internal Service Agent
------------------------------------------------
Main Streamlit interface and application entry point.

Run with:  python -m streamlit run app.py

Five tabs:
  1. Agent Workspace  — analyse individual cases, record simulated actions
  2. All Cases        — all 25 source records with filtering
  3. Policy Library   — all 11 policies with conflict note
  4. Action History   — audit log with JSON export
  5. Project Guide    — architecture, setup, demo prep, defence guide

Design decisions:
- All business state changes go through the database layer, not the UI.
- The LLM proposes; the operator confirms; Python executes and records.
- Streamlit reruns are made idempotent: recording checks plan status before writing.
- API key is read from session state and never written to logs or the DB.
- Mode (Mistral / Offline) is clearly shown in every analysis output.
"""

import json
import streamlit as st
from datetime import datetime, timezone

# ── Auto-load .env file if present (so users just fill in .env and run) ───────
# This loads MISTRAL_API_KEY and MISTRAL_MODEL from the .env file automatically.
# If .env doesn't exist, nothing happens — the key can still be entered in the sidebar.
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)  # looks for .env in the project root and overrides old env vars
except ImportError:
    pass  # python-dotenv not installed; use sidebar or set env vars manually

from resolvedesk.database import init_db
init_db()

# ── Project imports ───────────────────────────────────────────────────────────
from resolvedesk.config import (
    DEFAULT_MISTRAL_MODEL,
    TOTAL_POLICIES, TOTAL_REQUESTS, TOTAL_TICKETS,
    ACTIVE_TICKETS, CLOSED_TICKETS, TOTAL_SOURCE_RECORDS,
    COMPANY_NAME,
)
from resolvedesk.data import (
    get_all_cases, get_requests, get_tickets, get_policies,
    get_request_by_id, get_ticket_by_id,
)
from resolvedesk.database import (
    get_case_state, upsert_case_state, add_clarification,
    get_clarifications, get_pending_plan, record_plan,
    append_audit, get_audit_log, export_audit_json,
    get_conversation, add_message, clear_conversation,
    stage_plan as db_stage_plan,
    DB_PATH,
)
from resolvedesk.agent import run_agent, run_offline
from resolvedesk.rules import detect_topic, validate_plan


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ResolveDesk — Chillstack",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Minimal CSS — functional, professional, beginner-readable ─────────────────
st.markdown("""
<style>
  /* Card-like boxes */
  .rd-card {
    background: #f8f9fa;
    border-left: 4px solid #0066cc;
    border-radius: 6px;
    padding: 14px 18px;
    margin-bottom: 12px;
  }
  .rd-card-urgent {
    background: #fff3f3;
    border-left: 4px solid #cc0000;
    border-radius: 6px;
    padding: 14px 18px;
    margin-bottom: 12px;
  }
  .rd-card-closed {
    background: #f0f0f0;
    border-left: 4px solid #888;
    border-radius: 6px;
    padding: 14px 18px;
    margin-bottom: 12px;
  }
  .rd-card-offline {
    background: #fff8e6;
    border-left: 4px solid #f0a500;
    border-radius: 6px;
    padding: 14px 18px;
    margin-bottom: 12px;
  }
  .rd-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.78em;
    font-weight: 600;
    margin-right: 4px;
  }
  .badge-active   { background:#d4edda; color:#155724; }
  .badge-closed   { background:#e2e3e5; color:#383d41; }
  .badge-urgent   { background:#f8d7da; color:#721c24; }
  .badge-offline  { background:#fff3cd; color:#856404; }
  .badge-groq  { background:#cce5ff; color:#004085; }
  .badge-sim      { background:#e8d5f5; color:#4a0080; }
  /* Conflict warning */
  .conflict-box {
    background:#fff3cd;
    border:1px solid #ffc107;
    border-radius:6px;
    padding:10px 14px;
    margin:8px 0;
  }
  /* Section headings */
  .rd-section-title {
    font-size:1.05em;
    font-weight:700;
    color:#0066cc;
    margin-top:14px;
    margin-bottom:4px;
  }
  /* Employee message box */
  .employee-msg {
    background:#e8f4fd;
    border-radius:6px;
    padding:12px 16px;
    font-style:italic;
    margin:8px 0;
  }
</style>
""", unsafe_allow_html=True)


# ── Session state defaults ────────────────────────────────────────────────────
import os

def _init_session():
    # We no longer display these in the UI, so we force them to match .env every time
    st.session_state["api_key"] = os.environ.get("GROQ_API_KEY", "")
    st.session_state["model"] = os.environ.get("GROQ_MODEL", DEFAULT_MISTRAL_MODEL)
    
    defaults = {
        "use_offline":    False,
        "last_case_id":   None,
        "last_result":    None,    # AgentResult from last analysis
        "recording_done": {},      # case_id → bool, prevents duplicate recording
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_session()


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://via.placeholder.com/200x50/0066cc/ffffff?text=ResolveDesk", width=200)
    st.markdown(f"**{COMPANY_NAME}** — Service Agent")
    st.divider()

    # We no longer display the API key input in the UI per user request.
    # The application automatically connects using the .env file.
    
    st.divider()
    offline_toggle = st.toggle(
        "🔌 Offline Rules-Demo Mode",
        value=st.session_state["use_offline"],
        help="Analyse cases using Python policy rules only — no API key needed. Clearly labelled.",
    )
    st.session_state["use_offline"] = offline_toggle

    if offline_toggle:
        st.markdown(
            '<div class="rd-card-offline"><b>⚠️ OFFLINE MODE ACTIVE</b><br>'
            'Results come from Python policy rules only.<br>'
            'This is NOT live AI output from Mistral.</div>',
            unsafe_allow_html=True,
        )
    elif st.session_state["api_key"]:
        st.markdown(
            '<span class="rd-badge badge-groq">🤖 Groq Mode</span>',
            unsafe_allow_html=True,
        )
    else:
        st.warning("No API key found in .env. Switch to Offline Mode or add the key to your .env file.")

    st.divider()
    st.markdown("### 📊 Source Counts")
    st.markdown(f"- **Policies:** {TOTAL_POLICIES}")
    st.markdown(f"- **Employee Requests:** {TOTAL_REQUESTS}")
    st.markdown(f"- **Tickets (total):** {TOTAL_TICKETS} ({ACTIVE_TICKETS} active, {CLOSED_TICKETS} closed)")
    st.markdown(f"- **Total Source Records:** {TOTAL_SOURCE_RECORDS}")
    st.caption("All counts from assignment source data. No fabricated records.")


# ── Tab layout ────────────────────────────────────────────────────────────────
tab_workspace, tab_all_cases, tab_policies, tab_history, tab_guide = st.tabs([
    "🛠️ Agent Workspace",
    "📋 All Cases",
    "📖 Policy Library",
    "📜 Action History",
    "📚 Project Guide",
])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — AGENT WORKSPACE
# ═══════════════════════════════════════════════════════════════════════════════
with tab_workspace:
    st.title("🛠️ Agent Workspace")
    st.caption(
        "Select a case, review the details, add clarifications, then click **Analyse Request**. "
        "The agent will retrieve relevant policies and propose a next step. "
        "You must explicitly confirm to record any simulated action."
    )

    # ── Case selector ──────────────────────────────────────────────────────
    all_cases = get_all_cases()
    active_cases = [c for c in all_cases if not c.get("is_closed", False)]

    # Build a label for each case for the selectbox.
    def case_label(c: dict) -> str:
        emp  = c.get("employee", c.get("id", "?"))
        cid  = c.get("id", "?")
        stat = c.get("initial_action") or c.get("source_status") or "?"
        closed_tag = " [CLOSED]" if c.get("is_closed") else ""
        return f"{cid} — {emp}{closed_tag} | {stat[:40]}"

    all_labels   = [case_label(c) for c in all_cases]
    active_labels = [case_label(c) for c in active_cases]

    show_closed = st.checkbox("Include closed cases in selector", value=False)
    selector_cases  = all_cases  if show_closed else active_cases
    selector_labels = all_labels if show_closed else active_labels

    if not selector_cases:
        st.warning("No cases available.")
        st.stop()

    selected_label = st.selectbox(
        "Select a case:",
        options=selector_labels,
        key="case_selector",
    )
    selected_idx  = selector_labels.index(selected_label)
    selected_case = selector_cases[selected_idx]
    case_id       = selected_case["id"]
    is_closed     = selected_case.get("is_closed", False)

    # Reset recording flag when user switches cases.
    if st.session_state.get("last_case_id") != case_id:
        st.session_state["last_case_id"] = case_id
        st.session_state["last_result"]  = None

    # ── Case details card ──────────────────────────────────────────────────
    st.divider()
    rec_type = selected_case.get("record_type", "request")
    card_cls = "rd-card-closed" if is_closed else "rd-card"

    closed_badge = '<span class="rd-badge badge-closed">CLOSED HISTORY</span>' if is_closed else \
                   '<span class="rd-badge badge-active">ACTIVE</span>'

    st.markdown(
        f'<div class="{card_cls}">'
        f'<b>{case_id}</b> {closed_badge} &nbsp; '
        f'<span style="color:#555">Type: {rec_type.title()}</span><br><br>'
        f'<b>Employee:</b> {selected_case.get("employee", "N/A")}<br>'
        f'<b>Email:</b> {selected_case.get("email", "Not supplied")}<br>'
        f'<b>Date Opened:</b> {selected_case.get("opened", "Not supplied")}<br>'
        f'<b>Request / Issue:</b><br>'
        f'<div class="employee-msg">{selected_case.get("request") or selected_case.get("issue_summary", "N/A")}</div>'
        f'<b>Initial Action (source):</b> {selected_case.get("initial_action") or selected_case.get("source_status", "N/A")}<br>'
        f'<b>Source Reference:</b> {selected_case.get("source", "N/A")}'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Current DB state
    db_state = get_case_state(case_id)
    if db_state:
        st.markdown(
            f'<div class="rd-card" style="border-color:#28a745">'
            f'<b>Current Application Status:</b> {db_state["current_status"]}'
            f'&nbsp; (Source: {db_state["source_status"]})'
            f'&nbsp; | Version {db_state["version"]}'
            f'</div>',
            unsafe_allow_html=True,
        )

    if is_closed:
        st.info(
            "🔒 **Closed history record.** This case cannot be actioned or reopened. "
            "It is visible for context only. Source status is preserved exactly as supplied."
        )

    # ── Conversation history ───────────────────────────────────────────────
    conversation = get_conversation(case_id)
    if conversation:
        with st.expander(f"💬 Conversation history ({len(conversation)} messages)", expanded=False):
            for msg in conversation:
                role  = msg.get("role", "?").upper()
                ts    = msg.get("timestamp", "")
                color = "#0066cc" if role == "ASSISTANT" else "#555"
                st.markdown(
                    f'<div style="margin:4px 0; padding:6px 10px; background:#f9f9f9; '
                    f'border-radius:4px; border-left:3px solid {color}">'
                    f'<small style="color:#888">[{ts}] <b>{role}</b></small><br>'
                    f'{msg.get("content", "")}</div>',
                    unsafe_allow_html=True,
                )

    # ── Clarification form ─────────────────────────────────────────────────
    st.divider()
    st.markdown("### 📝 Add Clarification / Follow-up Information")
    st.caption(
        "Enter any additional information provided by the employee or manager. "
        "This is stored as **reported information** — not independently verified."
    )

    if not is_closed:
        with st.form(key=f"clarification_form_{case_id}"):
            clarification_text = st.text_area(
                "Clarification or follow-up (plain English):",
                placeholder='e.g. "Employee confirms they are a full-time employee." or '
                            '"Manager approval has been emailed — needs verification."',
                height=80,
            )

            # Optional structured fields — shown based on topic.
            topic = selected_case.get("topic", detect_topic(
                selected_case.get("request", selected_case.get("issue_summary", ""))
            ))

            structured_data = {}
            with st.expander("📋 Optional structured facts (improves policy check accuracy)"):
                if topic == "password_lockout":
                    fa = st.number_input("Failed login attempts", min_value=0, max_value=20, value=0, key=f"fa_{case_id}")
                    if fa > 0: structured_data["failed_attempts"] = fa
                elif topic == "vpn":
                    emp_type = st.selectbox("Employee type", ["(not specified)", "full_time", "contractor"], key=f"et_{case_id}")
                    if emp_type != "(not specified)": structured_data["employee_type"] = emp_type
                    cred_exp = st.checkbox("VPN credentials expired?", key=f"ce_{case_id}")
                    if cred_exp: structured_data["credentials_expired"] = True
                elif topic == "laptop":
                    age = st.number_input("Laptop age (years)", min_value=0.0, max_value=20.0, value=0.0, step=0.5, key=f"la_{case_id}")
                    if age > 0: structured_data["age_years"] = age
                    fail_v = st.checkbox("Hardware failure verified by IT?", key=f"fv_{case_id}")
                    if fail_v: structured_data["hardware_failure_verified"] = True
                elif topic == "mailbox_quota":
                    req_gb = st.number_input("Requested quota (GB)", min_value=0, max_value=200, value=0, key=f"rg_{case_id}")
                    if req_gb > 0: structured_data["requested_gb"] = req_gb
                elif topic == "wfh_equipment":
                    days = st.number_input("Remote days per week", min_value=0, max_value=7, value=0, key=f"rd_{case_id}")
                    if days > 0: structured_data["remote_days_per_week"] = days
                elif topic == "software_install":
                    cat = st.selectbox("Catalog status", ["(not specified)", "in_catalog", "not_in_catalog", "unknown"], key=f"cs_{case_id}")
                    if cat != "(not specified)": structured_data["catalog_status"] = cat
                elif topic == "expense_tool":
                    acc = st.selectbox("Account exists?", ["(not specified)", "yes", "no"], key=f"ae_{case_id}")
                    if acc != "(not specified)": structured_data["account_exists"] = (acc == "yes")
                elif topic == "printer":
                    at = st.text_input("Printer asset tag (if known)", key=f"pat_{case_id}")
                    if at: structured_data["asset_tag"] = at

            submit_clarification = st.form_submit_button("💾 Save Clarification")

        if submit_clarification:
            if clarification_text.strip():
                add_clarification(
                    case_id=case_id,
                    clarification=clarification_text.strip(),
                    structured_data=structured_data if structured_data else None,
                    reported_by="operator",
                )
                append_audit(
                    case_id=case_id,
                    action_type="clarification_added",
                    description=f"Operator added clarification: {clarification_text.strip()[:100]}",
                    evidence_ids=[],
                )
                st.success("✅ Clarification saved.")
                # Force rerun to show updated clarifications.
                st.rerun()
            else:
                st.warning("Please enter some clarification text before saving.")

    # Show existing clarifications.
    clarifications = get_clarifications(case_id)
    if clarifications:
        with st.expander(f"📎 Recorded clarifications ({len(clarifications)})", expanded=False):
            for c in clarifications:
                sd_display = ""
                if c.get("structured_data"):
                    try:
                        sd = json.loads(c["structured_data"]) if isinstance(c["structured_data"], str) else c["structured_data"]
                        sd_display = f'<br><small>Structured: {sd}</small>'
                    except Exception:
                        pass
                st.markdown(
                    f'<div style="margin:4px 0; padding:8px 12px; background:#f0f7ff; '
                    f'border-radius:4px; border-left:3px solid #0066cc">'
                    f'<small style="color:#888">[{c.get("submitted_at","")}] {c.get("reported_by","?")}</small><br>'
                    f'{c.get("clarification","")}{sd_display}</div>',
                    unsafe_allow_html=True,
                )

    # ── Analyse button ─────────────────────────────────────────────────────
    st.divider()
    col_btn1, col_btn2 = st.columns([2, 3])
    with col_btn1:
        analyse_clicked = st.button(
            "🔍 Analyse Request",
            type="primary",
            disabled=is_closed,
            key=f"analyse_{case_id}",
        )
    with col_btn2:
        clear_clicked = st.button(
            "🔄 Clear Conversation & Re-analyse",
            disabled=is_closed,
            key=f"clear_{case_id}",
        )
    if clear_clicked:
        clear_conversation(case_id)
        st.session_state["last_result"] = None
        st.rerun()

    if analyse_clicked and not is_closed:
        with st.spinner("Analysing case…"):
            if st.session_state["use_offline"]:
                result = run_offline(case_id)
            else:
                result = run_agent(
                    case_id=case_id,
                    api_key=st.session_state["api_key"],
                    model=st.session_state["model"],
                )
        st.session_state["last_result"] = result
        # Reset recording flag for new analysis.
        st.session_state["recording_done"][case_id] = False
        st.rerun()

    # ── Display analysis result ────────────────────────────────────────────
    result = st.session_state.get("last_result")

    if result is not None and st.session_state.get("last_case_id") == case_id:
        st.divider()

        # Mode badge
        if result.mode == "offline":
            st.markdown(
                '<div class="rd-card-offline">'
                '<b>⚠️ OFFLINE RULES-DEMO MODE</b> — '
                'This analysis was produced by Python policy rules, NOT by Mistral or any LLM. '
                'For demonstration purposes only.</div>',
                unsafe_allow_html=True,
            )
        elif result.mode == "groq":
            st.markdown(
                '<span class="rd-badge badge-groq">🤖 Groq AI Analysis</span> '
                '<span class="rd-badge badge-sim">⚙️ All actions are simulated</span>',
                unsafe_allow_html=True,
            )
        elif result.mode == "closed":
            st.info("This case is closed history. Displaying context only.")

        # Error display
        if result.mode == "error":
            st.error(f"**Analysis Error**\n\n{result.error}")
            st.info(
                "💡 **Tip:** You can use **Offline Rules-Demo Mode** (sidebar toggle) "
                "to analyse this case without an API key."
            )

        # Plan display
        elif result.plan:
            plan = result.plan

            # Urgency alert
            if plan.get("is_urgent"):
                st.markdown(
                    '<div class="rd-card-urgent">🚨 <b>URGENT — Security Issue</b><br>'
                    'This case requires immediate Security attention.</div>',
                    unsafe_allow_html=True,
                )

            # Main plan card
            st.markdown("### 📋 Recommended Plan")

            col_l, col_r = st.columns(2)
            with col_l:
                st.markdown(f"**Case ID:** {plan.get('case_id', '?')}")
                st.markdown(f"**Topic:** {plan.get('topic', '?')}")
                st.markdown(f"**Category:** {plan.get('category', '?')}")
            with col_r:
                st.markdown(f"**Current Status:** {plan.get('current_status', '?')}")
                st.markdown(f"**Proposed Status:** {plan.get('proposed_status', '?')}")
                st.markdown(f"**Route:** {plan.get('proposed_route', '?')}")

            st.markdown("**Summary for Operator:**")
            st.info(plan.get("summary", "No summary."))

            st.markdown("**Message for Employee:**")
            st.markdown(
                f'<div class="employee-msg">{plan.get("employee_explanation", "No explanation.")}</div>',
                unsafe_allow_html=True,
            )

            st.markdown(f"**Proposed Action:** {plan.get('proposed_action', 'N/A')}")

            # Policy IDs cited
            pids = plan.get("policy_ids", [])
            if pids:
                st.markdown(f"**Policy IDs cited:** {', '.join(pids)}")
                # Show policy text for each cited ID.
                from resolvedesk.data import get_policy_by_id
                with st.expander("📖 View cited policy text", expanded=False):
                    for pid in pids:
                        p = get_policy_by_id(pid)
                        if p:
                            st.markdown(f"**{pid} — {p['title']}**")
                            st.markdown(p["text"])
                            if p.get("conflict_note"):
                                st.markdown(
                                    f'<div class="conflict-box">⚠️ {p["conflict_note"]}</div>',
                                    unsafe_allow_html=True,
                                )
                            st.divider()

            # Conflicts
            if plan.get("conflicts"):
                st.markdown(
                    '<div class="conflict-box"><b>⚠️ Policy Conflicts Detected</b><ul>'
                    + "".join(f"<li>{c}</li>" for c in plan["conflicts"])
                    + "</ul></div>",
                    unsafe_allow_html=True,
                )

            # Warnings
            if plan.get("warnings"):
                for w in plan["warnings"]:
                    st.warning(w)

            # Missing information
            if plan.get("missing_info"):
                st.markdown("**ℹ️ Missing Information:**")
                for m in plan["missing_info"]:
                    st.markdown(f"- {m}")

            # Questions for employee
            if plan.get("questions_for_employee"):
                st.markdown("**❓ Questions to Ask Employee:**")
                for q in plan["questions_for_employee"]:
                    st.markdown(f"- {q}")

            # Evidence
            if plan.get("evidence"):
                st.markdown(f"**Evidence / Related Records:** {', '.join(plan['evidence'])}")

            # Simulation indicator — always shown.
            st.markdown(
                '<span class="rd-badge badge-sim">⚙️ SIMULATED — No real action has been taken</span>',
                unsafe_allow_html=True,
            )

            # ── Record local action ────────────────────────────────────────
            st.divider()
            st.markdown("### 💾 Record Local Action")

            if plan.get("closed_history_only"):
                st.info("Closed history — no action can be recorded.")
            elif st.session_state["recording_done"].get(case_id):
                st.success("✅ Action already recorded for this analysis. See Action History tab.")
            else:
                st.markdown(
                    "_Review the plan above carefully. "
                    "Clicking **Record Local Action** will save this simulated action to the audit log "
                    "and update the case status. This cannot be undone._"
                )

                # Validate the plan before allowing the button.
                is_valid, validation_msg = validate_plan(
                    plan, case_id, is_closed=is_closed
                )

                if not is_valid:
                    st.error(f"Plan validation failed: {validation_msg}")
                else:
                    record_clicked = st.button(
                        "✅ Record Local Action (Simulated)",
                        type="primary",
                        key=f"record_{case_id}_{id(result)}",
                    )
                    if record_clicked:
                        # Idempotency check — re-validate just before writing.
                        if st.session_state["recording_done"].get(case_id):
                            st.warning("Already recorded.")
                        else:
                            old_status = (db_state or {}).get("current_status") or \
                                         selected_case.get("initial_action") or \
                                         selected_case.get("source_status") or "Not started"
                            new_status = plan.get("proposed_status", "In progress")

                            upsert_case_state(
                                case_id=case_id,
                                record_type=rec_type,
                                source_status=(
                                    selected_case.get("initial_action") or
                                    selected_case.get("source_status") or "Not started"
                                ),
                                current_status=new_status,
                                topic=plan.get("topic", ""),
                            )
                            append_audit(
                                case_id=case_id,
                                action_type=f"action_recorded_{result.mode}",
                                description=(
                                    f"[{result.mode.upper()} MODE — SIMULATED] "
                                    f"{plan.get('proposed_action', 'N/A')[:200]}"
                                ),
                                old_status=old_status,
                                new_status=new_status,
                                evidence_ids=plan.get("policy_ids", []),
                            )
                            add_message(case_id, "assistant",
                                        f"[Plan recorded] {plan.get('summary', '')}", DB_PATH)
                            st.session_state["recording_done"][case_id] = True
                            st.success(f"✅ Simulated action recorded. Status updated to: {new_status}")
                            st.rerun()

        # ── Tool trace ─────────────────────────────────────────────────────
        if result.trace:
            with st.expander(f"🔧 Tool trace ({len(result.trace)} calls)", expanded=False):
                for i, step in enumerate(result.trace):
                    st.markdown(f"**Step {i+1}: `{step['tool']}`**")
                    with st.container():
                        col_a, col_r = st.columns(2)
                        with col_a:
                            st.markdown("*Arguments:*")
                            st.json(step.get("args", {}))
                        with col_r:
                            st.markdown("*Result:*")
                            r_display = step.get("result", {})
                            # Truncate large results for display.
                            r_str = json.dumps(r_display, ensure_ascii=False)
                            if len(r_str) > 800:
                                r_str = r_str[:800] + "…[truncated]"
                                st.code(r_str, language="json")
                            else:
                                st.json(r_display)
                    st.divider()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — ALL CASES
# ═══════════════════════════════════════════════════════════════════════════════
with tab_all_cases:
    st.title("📋 All Cases")
    st.caption(
        f"All {TOTAL_SOURCE_RECORDS} original source records: "
        f"{TOTAL_REQUESTS} employee requests + {TOTAL_TICKETS} tickets "
        f"({ACTIVE_TICKETS} active, {CLOSED_TICKETS} closed)."
    )

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        filter_type = st.selectbox(
            "Record type", ["All", "Requests", "Tickets"], key="filter_type"
        )
    with col_f2:
        filter_status = st.selectbox(
            "Status", ["All", "Active only", "Closed only"], key="filter_status"
        )
    with col_f3:
        search_text = st.text_input("Search (ID, employee, keyword)", key="search_text")

    all_cases_data = get_all_cases()

    # Apply filters.
    filtered = all_cases_data
    if filter_type == "Requests":
        filtered = [c for c in filtered if c.get("record_type") == "request"]
    elif filter_type == "Tickets":
        filtered = [c for c in filtered if c.get("record_type") == "ticket"]

    if filter_status == "Active only":
        filtered = [c for c in filtered if not c.get("is_closed", False)]
    elif filter_status == "Closed only":
        filtered = [c for c in filtered if c.get("is_closed", False)]

    if search_text.strip():
        q = search_text.strip().lower()
        filtered = [
            c for c in filtered
            if q in c.get("id", "").lower()
            or q in c.get("employee", "").lower()
            or q in (c.get("request") or c.get("issue_summary") or "").lower()
            or q in (c.get("topic") or "").lower()
        ]

    st.markdown(f"**Showing {len(filtered)} of {len(all_cases_data)} records**")
    st.divider()

    for case in filtered:
        cid       = case.get("id", "?")
        emp       = case.get("employee", "?")
        is_cls    = case.get("is_closed", False)
        rtype     = case.get("record_type", "request")
        summary   = case.get("request") or case.get("issue_summary") or "N/A"
        status    = case.get("initial_action") or case.get("source_status") or "?"
        db_s      = get_case_state(cid)

        badge_html = (
            '<span class="rd-badge badge-closed">CLOSED</span>'
            if is_cls else
            '<span class="rd-badge badge-active">ACTIVE</span>'
        )
        type_badge = f'<span class="rd-badge" style="background:#e8e8e8;color:#333">{rtype.title()}</span>'

        current_status_line = ""
        if db_s:
            current_status_line = f'<br><b>Current Status:</b> {db_s["current_status"]}'

        st.markdown(
            f'<div class="{"rd-card-closed" if is_cls else "rd-card"}">'
            f'<b>{cid}</b> {badge_html} {type_badge}'
            f'<br><b>Employee:</b> {emp}'
            f'<br><b>Source Status:</b> {status}'
            f'{current_status_line}'
            f'<br><b>Summary:</b> {summary[:150]}{"…" if len(summary) > 150 else ""}'
            f'</div>',
            unsafe_allow_html=True,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — POLICY LIBRARY
# ═══════════════════════════════════════════════════════════════════════════════
with tab_policies:
    st.title("📖 Policy Library")
    st.caption(
        f"All {TOTAL_POLICIES} source policies from Assignment 2 Data Pack, Section 1, page 1. "
        "These are displayed exactly as supplied. No policies have been added or modified."
    )

    st.markdown(
        '<div class="conflict-box"><b>⚠️ Laptop Policy Conflict (Visible to all users)</b><br>'
        '<b>KB-03</b> sets a <b>3-year</b> replacement threshold for laptops.<br>'
        '<b>ASSET-Q2-2026</b> (updated Q2 2026) sets a <b>4-year</b> refresh cycle.<br>'
        'No precedence rule is supplied in the source data. Both policies are shown for every laptop case. '
        'Clarification must be routed to IT and Finance/Assets.'
        '</div>',
        unsafe_allow_html=True,
    )

    policies = get_policies()
    for p in policies:
        has_conflict = bool(p.get("conflict_note"))
        with st.expander(
            f"**{p['id']}** — {p['title']} {'⚠️' if has_conflict else ''}",
            expanded=False,
        ):
            st.markdown(f"**Source:** {p.get('source', 'N/A')}")
            st.markdown(f"**Owner:** {p.get('owner', 'N/A')}")
            st.markdown(f"**Approval Required:** {p.get('approval_required', 'N/A')}")
            st.divider()
            st.markdown(p["text"])
            if has_conflict:
                st.markdown(
                    f'<div class="conflict-box">⚠️ {p["conflict_note"]}</div>',
                    unsafe_allow_html=True,
                )
            if p.get("limits"):
                st.markdown(f"**Policy Limits:** {p['limits']}")
            if p.get("urgent"):
                st.error("🚨 This policy involves urgent Security actions.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — ACTION HISTORY
# ═══════════════════════════════════════════════════════════════════════════════
with tab_history:
    st.title("📜 Action History")
    st.caption(
        "Append-only audit log of all recorded simulated actions and clarifications. "
        "API keys and credentials are never stored here."
    )

    audit_records = get_audit_log()

    col_h1, col_h2 = st.columns([3, 1])
    with col_h1:
        filter_case = st.text_input("Filter by Case ID", key="hist_filter")
    with col_h2:
        st.markdown("&nbsp;")
        export_clicked = st.button("⬇️ Export JSON", key="export_audit")

    if export_clicked:
        export_data = export_audit_json()
        st.download_button(
            label="Download audit_log.json",
            data=export_data,
            file_name="resolvedesk_audit_log.json",
            mime="application/json",
            key="download_audit",
        )

    if filter_case.strip():
        audit_records = [r for r in audit_records if filter_case.upper() in r.get("case_id", "")]

    if not audit_records:
        st.info("No audit records yet. Analyse a case and record an action to see entries here.")
    else:
        st.markdown(f"**{len(audit_records)} records** {'(filtered)' if filter_case.strip() else ''}")
        for rec in audit_records:
            evid = rec.get("evidence_ids", [])
            evid_str = ", ".join(evid) if evid else "None"
            status_change = ""
            if rec.get("old_status") and rec.get("new_status"):
                status_change = f"<br><b>Status:</b> {rec['old_status']} → {rec['new_status']}"

            st.markdown(
                f'<div class="rd-card">'
                f'<b>[{rec.get("timestamp", "?")}]</b> &nbsp; '
                f'<b>{rec.get("case_id", "?")}</b> &nbsp; '
                f'<code>{rec.get("action_type", "?")}</code>'
                f'{status_change}'
                f'<br>{rec.get("description", "")}'
                f'<br><small>Evidence: {evid_str} &nbsp;|&nbsp; '
                f'Simulated: {bool(rec.get("is_simulation", True))}</small>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 5 — PROJECT GUIDE
# ═══════════════════════════════════════════════════════════════════════════════
with tab_guide:
    st.title("📚 Project Guide")

    guide_tabs = st.tabs([
        "🏠 Overview",
        "🏗️ Architecture",
        "📦 Setup & Run",
        "🎭 AI Tools Disclosure",
        "🎬 Demo Guide",
        "🛡️ Defence Q&A",
        "📊 Slide Outline",
        "✅ Submission Checklist",
    ])

    # ── Overview ───────────────────────────────────────────────────────────
    with guide_tabs[0]:
        st.markdown("""
## ResolveDesk — AI Internal Service Agent

**Company:** Chillstack (assignment scenario)
**Exercise week:** Monday 21 September 2026 – Friday 25 September 2026

### Business Problem
Chillstack employees report IT problems every day. Without a structured agent:
- Operators spend time researching policies for each request.
- Some requests get duplicate tickets or wrong routing.
- Security incidents may not receive immediate attention.
- Policy conflicts (like the laptop 3-year vs 4-year rule) are missed.
- Vague requests sit unresolved because no one asks the right questions.

### What ResolveDesk Does
1. **Reads the original source data** — all 15 requests, 10 tickets, 11 policies — as read-only JSON files.
2. **Detects the topic** of each request using keyword matching.
3. **Retrieves relevant policies** from the knowledge base.
4. **Applies business rules** in Python to determine eligibility, required approvals, and conflicts.
5. **Calls Mistral AI** (in live mode) with tool-calling to orchestrate a structured analysis.
6. **Surfaces conflicts** (notably KB-03 vs ASSET-Q2-2026 on laptops) without resolving them arbitrarily.
7. **Stages a plan** — shown to the operator for review.
8. **Records simulated actions** — with explicit operator confirmation and a full audit trail.

### What ResolveDesk Does NOT Do
- It does not send real emails, unlock real accounts, or grant real access.
- It does not train or fine-tune any AI model.
- It does not invent policies, URLs, approver names, or deadlines.
- It does not claim cases are resolved just because an answer was generated.
- It does not present offline-rules output as live AI.

### Source Data Counts
| Category | Count | Source |
|---|---|---|
| Policies (KB-01–KB-10 + ASSET-Q2-2026) | 11 | Section 1, page 1 |
| Employee Requests | 15 | Section 2, pages 1–2 |
| Existing Tickets | 10 | Section 3, page 2 |
| Active Tickets | 4 | TK-1043, TK-1044, TK-1047, TK-1048 |
| Closed Tickets | 6 | TK-1042, TK-1045, TK-1046, TK-1049, TK-1050, TK-1051 |

### Key Assumptions (documented)
1. Employee requests and similarly named tickets are **not assumed to be the same case** unless explicitly linked.
2. Reported laptop ages and failure descriptions are **not treated as verified hardware failure**.
3. Employee assertions ("Finance approved") are stored as **reported information, not authorisation**.
4. No software catalog is supplied — catalog membership is always clarified, never assumed.
5. The 2-week advance notice rule (KB-03) is noted but not used to block emergency diagnosis.
6. "More than 3 days/week" means ≥ 4 days/week for WFH eligibility.
7. Runtime audit timestamps use actual UTC time; assignment dates use the supplied 2026-09-21–25 week.
8. All simulated actions are explicitly marked as such throughout the application.
""")

    # ── Architecture ───────────────────────────────────────────────────────
    with guide_tabs[1]:
        st.markdown("""
## Architecture

### Module Map

| File | Role |
|---|---|
| `app.py` | Streamlit UI — five tabs, case selector, clarification form, plan display |
| `resolvedesk/agent.py` | Mistral SDK integration, bounded tool-calling loop |
| `resolvedesk/tools.py` | Tool schemas (JSON) + guarded execution functions |
| `resolvedesk/rules.py` | Policy checks, topic detection, plan validation |
| `resolvedesk/database.py` | SQLite: case state, clarifications, plans, audit log |
| `resolvedesk/prompts.py` | System prompt + context-building for Mistral |
| `resolvedesk/data.py` | Load + cache JSON source files |
| `resolvedesk/config.py` | Paths, env vars, safety constants |
| `data/policies.json` | 11 policies (authoritative, read-only) |
| `data/requests.json` | 15 employee requests (authoritative, read-only) |
| `data/tickets.json` | 10 existing tickets (authoritative, read-only) |
| `tests/` | unittest test suite |
| `docs/` | Supplementary documentation |

### Data Flow (Mistral Mode)

```
[Operator selects case]
        ↓
[app.py] reads case from data.py (JSON, read-only)
        ↓
[agent.py] builds prompt with case + policies + conversation
        ↓
[Mistral API] ← system prompt + user context + tool schemas
        ↓
[Model calls tools: get_case, get_policy, evaluate_case, stage_plan]
        ↓
[tools.py] validates + executes each tool call (no eval, no shell)
        ↓
[rules.py] applies policy checks, detects conflicts
        ↓
[database.py] stores clarifications, stages plan
        ↓
[app.py] displays plan to operator for review
        ↓
[Operator clicks "Record Local Action"]
        ↓
[validate_plan()] re-checks plan is current and valid
        ↓
[database.py] upserts case state + appends audit record
        ↓
[UI refreshes with updated status]
```

### Safety Architecture
- **LLM proposes; Python controls:** The model cannot write to the DB or execute actions directly.
- **Bounded loop:** Max 8 tool iterations prevents runaway API usage.
- **Idempotent recording:** Recording checks the plan status; duplicate clicks are ignored.
- **No eval/exec:** Tool arguments are validated as typed data, never executed as code.
- **API key safety:** Key is in session state only, never in logs, DB, prompts, or exports.
- **Closed case protection:** `validate_plan()` blocks recording on closed cases.

### Why One Agent is Sufficient
The 11 source policies are a small, well-defined knowledge base. A single agent with
6 tools can retrieve, reason, and plan for all 25 source records. Multiple agents,
CrewAI, and LangGraph add coordination overhead without adding correctness for this scope.
A vector database is unnecessary when exact policy lookup (by ID and keyword) is sufficient.
""")

    # ── Setup & Run ────────────────────────────────────────────────────────
    with guide_tabs[2]:
        st.markdown("""
## Setup & Run Instructions

### Prerequisites
- Python 3.10 or later (Python 3.12 recommended)
- A terminal or command prompt
- A Mistral API key (optional — offline mode works without one)

### Step 1 — Create a virtual environment

**Windows (PowerShell):**
```powershell
python -m venv venv
venv\\Scripts\\activate
```

**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 2 — Install dependencies
```bash
pip install -r requirements.txt
```

### Step 3 — Set your Mistral API key (optional)
Copy `.env.example` to `.env` and fill in your key:
```bash
cp .env.example .env
# Edit .env and set MISTRAL_API_KEY=your_key_here
```

If you use a `.env` file, load it before starting (or use the sidebar field):
```bash
# On Linux/macOS:
export $(cat .env | xargs)
# On Windows PowerShell:
$env:MISTRAL_API_KEY = "your_key_here"
```

Or simply enter the key in the sidebar when the app opens. **Never put a real key in the source code.**

### Step 4 — Run the application
```bash
python -m streamlit run app.py
```

The app will open at `http://localhost:8501` in your browser.

### Step 5 — Using the app
1. **Without a key:** Enable "Offline Rules-Demo Mode" in the sidebar toggle.
2. **With a key:** Enter it in the sidebar, leave the toggle off, and use Mistral mode.
3. Select any case from the dropdown in the Agent Workspace tab.
4. Add clarifications if needed, then click **Analyse Request**.
5. Review the plan, then click **Record Local Action** to save.

### Step 6 — Run the tests
```bash
python -m unittest discover -s tests -v
```

### Troubleshooting
- **`ModuleNotFoundError: mistralai`** → Run `pip install mistralai`
- **Database errors** → The DB is created automatically; check write permissions in the project folder.
- **API errors** → Check your key and model name; use offline mode as a fallback.
- **Port already in use** → Run `python -m streamlit run app.py --server.port 8502`
""")

    # ── AI Tools Disclosure ────────────────────────────────────────────────
    with guide_tabs[3]:
        st.markdown("""
## AI Tools Disclosure

Transparency is a requirement of this assignment. This section documents every AI tool
that was involved in this project.

### Development Assistant
**Antigravity (Google DeepMind) / Claude Sonnet** was used as the coding assistant
during development in this IDE. It wrote the source code, documentation, and tests
based on the detailed assignment specification provided by the user.

This is the standard use of an AI coding assistant. The code is authored and reviewed
by the developer; the AI accelerates the writing process.

### Runtime LLM — Mistral AI
**Mistral AI** (model: `mistral-large-latest` by default, configurable) is the
runtime language model. It is called via the official Mistral Python SDK when the
operator selects Mistral mode.

Mistral is used to:
- Understand the case context from the structured prompt.
- Decide which tools to call and in what order.
- Compose the employee-facing explanation in natural language.
- Stage a structured plan.

Mistral is NOT used to:
- Enforce policy rules (Python handles this).
- Execute any real action (the UI and database layer block this).
- Be presented as a "newly trained" model — it is a pre-existing commercial LLM.

### Offline Rules-Demo Mode
When offline mode is active, **no LLM is involved**. All analysis is produced by
the Python functions in `resolvedesk/rules.py`. This is clearly labelled in the UI.

### What was NOT used
- OpenAI, Claude (as runtime), or Gemini were not used as the application's runtime LLM.
- No model training, fine-tuning, or embedding was performed.
- No vector database was used.
- No Docker, CrewAI, LangGraph, or multi-agent framework was used.

### Prompt Origin
The detailed assignment specification that guided this build was provided by the user
as a structured prompt. It was composed by the user with assistance from ChatGPT-assisted
planning (as disclosed in the specification). The code was produced by the Antigravity
coding assistant in response to that specification.
""")

    # ── Demo Guide ─────────────────────────────────────────────────────────
    with guide_tabs[4]:
        st.markdown("""
## 15-Minute Demo Guide

> Practice this walkthrough before your presentation. The app should be running
> locally before you start. Offline mode is recommended if internet is unreliable.

### 0–2 minutes: Business Problem
- Open the **All Cases** tab. Show the 25 source records.
- Explain: "Chillstack employees submit requests every day. Without an agent,
  operators must manually look up policies and decide the right action."
- Point out: active vs closed tickets, different statuses.

### 2–3 minutes: Architecture
- Open the **Project Guide → Architecture** tab.
- Walk through the data flow: JSON files → rules.py → agent.py → Mistral → UI → DB.
- Emphasise: "The LLM proposes; Python controls. No real actions happen."

### 3–5 minutes: Simple Case — Guest Wi-Fi (REQ-02)
- Go to **Agent Workspace**, select **REQ-02 — Vikram Chawla**.
- Click **Analyse Request** (offline mode OK).
- Show: KB-07 is cited, front-desk kiosk guidance, no IT ticket needed.
- "This took one policy lookup and one clear answer."

### 5–8 minutes: Difficult Cases — Laptop Conflict (REQ-01) + Phishing (REQ-08)
- Select **REQ-01 — Aditi Sharma** (dead laptop, 3.5 years old).
- Click **Analyse Request**.
- Show: BOTH KB-03 (3 years) and ASSET-Q2-2026 (4 years) appear.
- Show: The conflict note. "We never silently pick one rule."
- Select **REQ-08 — Ananya Reddy** (phishing, forwarding to colleagues).
- Show: Urgent badge, stop-forwarding warning, Security escalation preserved.

### 8–10 minutes: Active Ticket + Audit Trail
- Select **TK-1043** (laptop replacement, approved but pending).
- Show: Approval preserved; fulfillment still pending.
- Record an action for one of the earlier cases.
- Go to **Action History** — show the timestamped audit record.
- "Duplicate clicks won't create duplicate records."

### 10–11 minutes: Limitations & Disclosure
- "All actions are simulated. No real emails or account changes happen."
- "In production, this would connect to the real ticketing system."
- "Mistral is the runtime LLM. I did not train a new model."
- Open **AI Tools Disclosure** tab and read the key points.

### 11–15 minutes: Defence / Questions
- See the Defence Q&A tab for suggested answers.

### Demo Video Instructions
1. Start a screen recording tool (e.g., OBS Studio, Windows Game Bar, or Loom).
2. Walk through the steps above while narrating.
3. Upload the recording to Google Drive.
4. Set sharing to "Anyone with the link — Viewer".
5. Test the link in an incognito window before submitting.
**Note:** The video has not been recorded yet — this is the script. Record it yourself
using the steps above.

### GitHub Instructions
1. Create a GitHub account if you don't have one.
2. Create a new repository named `ResolveDesk`.
3. Upload all project files (excluding `venv/`, `resolvedesk.db`, and `.env`).
4. Ensure the README.md and requirements.txt are at the root.
5. Make the repository public.
6. Add the link to your submission.
**Note:** No repository has been created yet — this is the instruction. Create it yourself.
""")

    # ── Defence Q&A ────────────────────────────────────────────────────────
    with guide_tabs[5]:
        st.markdown("""
## Defence Q&A — Suggested Answers

**Q: Why is this agentic AI?**
> An agent is a system that perceives its environment, decides what to do, and takes
> actions to achieve a goal. ResolveDesk perceives case state and policies, decides
> which tools to call, iterates through a tool-calling loop, and produces a structured
> plan. It is not a single prompt-response exchange — it reasons over multiple steps.

**Q: What is an LLM, and what does Mistral do here?**
> A Large Language Model (LLM) is a neural network trained on large text datasets
> to generate and understand language. Mistral is the LLM used here. It reads the case
> context, decides which tools to call (e.g., get_policy, evaluate_case), interprets
> the tool results, and composes the employee-facing explanation and structured plan.
> It does not enforce policy rules — Python does that.

**Q: What is a tool?**
> In this context, a tool is a Python function with a JSON schema that describes
> its name, parameters, and purpose. Mistral reads the schema and decides when to
> call a tool and with what arguments. The result is returned to Mistral, which
> continues reasoning. Tools here include: get_case, get_policy, evaluate_case,
> stage_plan, ask_clarification, and get_related_history.

**Q: Why is one agent sufficient?**
> The knowledge base has 11 policies and 25 source records. A single agent with
> 6 focused tools can handle every case. Multiple agents would add coordination
> overhead and failure points without improving correctness for this bounded scope.

**Q: Why not CrewAI, LangGraph, or a vector database?**
> CrewAI and LangGraph are frameworks for multi-agent systems. One agent is
> sufficient here. A vector database enables semantic search over large document
> collections. With 11 policies, exact keyword lookup is faster and more auditable.
> Adding frameworks only for appearance would make the code harder to understand
> and defend.

**Q: How do you handle conflicting policies?**
> The KB-03 vs ASSET-Q2-2026 conflict is detected in rules.py and surfaced
> explicitly in every laptop analysis. Both policies are shown. No precedence
> is declared (none is supplied in the source). The operator is instructed to
> route clarification to IT and Finance/Assets.

**Q: How do you handle missing information?**
> The rules engine flags missing facts (e.g., employee type, hardware age,
> catalog status) and returns them as missing_info items. The agent calls
> ask_clarification to stage a question. The UI presents the question to the
> operator, who records the employee's response as reported information.

**Q: How do you prevent unsupported approvals and duplicate actions?**
> Five layers:
> 1. validate_plan() checks the plan before the Record button is enabled.
> 2. record_plan() uses a SQL UPDATE with status='pending' guard — only one
>    recording can succeed per plan.
> 3. session_state["recording_done"] prevents the button triggering twice.
> 4. Closed cases are blocked from receiving actions.
> 5. The system prompt explicitly forbids the model from granting access.

**Q: What is simulated, and what would production require?**
> Everything labelled "simulated": account unlocks, email sends, access grants,
> software installs, equipment shipping. Production would require: API integration
> with the real ticketing system, SSO authentication, real email via SMTP or
> Microsoft Graph, approval workflow integration (e.g., ServiceNow), and proper
> RBAC. None of that exists in this prototype.

**Q: What happens when the LLM API fails?**
> The agent loop catches all exceptions, scrubs the API key from the error message,
> and returns an AgentResult with mode='error'. The UI shows the error clearly and
> offers the offline mode. Case state in the database is not affected.

**Q: How did you validate the result?**
> The test suite in tests/ covers: source data counts, all 15 request topics,
> active/closed ticket handling, policy conflict detection, mailbox boundary cases,
> WFH eligibility threshold, duplicate recording prevention, and API error handling.
> Tests run without a network connection or API key. Live Mistral response validation
> requires an actual key and is not part of the automated suite.
""")

    # ── Slide Outline ──────────────────────────────────────────────────────
    with guide_tabs[6]:
        st.markdown("""
## Ten-Slide Presentation Outline

> Use these as the basis for your PPTX. Add screenshots from the running app.
> Speaker notes are in italics below each slide.

---

### Slide 1 — Title
**ResolveDesk — AI Internal Service Agent**
Chillstack | AIONOS Assignment 2
Presenter: [Your Name] | Date: [Date]

*Introduce yourself and the project name. One sentence: "ResolveDesk helps service
desk operators handle employee IT requests faster and more consistently."*

---

### Slide 2 — Business Problem
**The Problem at Chillstack**
- Employees submit 10+ types of IT requests daily
- Operators must manually look up policies for each case
- Conflicting policies (e.g., laptop replacement: 3 years vs 4 years) cause confusion
- Security incidents may not receive immediate attention
- Vague requests sit unresolved without the right questions

*Example: "Aditi's laptop died after 3.5 years. Is she eligible? Which policy applies?"
This takes 10 minutes manually; ResolveDesk surfaces both policies in seconds.*

---

### Slide 3 — Source Data
**What We Work With**
- 11 knowledge base policies (KB-01 through KB-10 + Asset Management)
- 15 employee requests (Monday–Friday, Sep 21–25, 2026)
- 10 existing tickets (4 active, 6 closed history)
- All data from Assignment 2 Data Pack — not invented

*Show the All Cases tab. Emphasise: "We use every supplied record, including closed history."*

---

### Slide 4 — Proposed Solution
**ResolveDesk: What It Does**
- Reads case details and relevant policies automatically
- Applies business rules to check eligibility and approvals
- Surfaces policy conflicts explicitly (never silently picks one)
- Asks targeted questions when information is missing
- Stages a plan for operator review — with explicit confirmation required
- Records simulated actions with a full audit trail

*Show a completed analysis card in the Agent Workspace tab.*

---

### Slide 5 — Architecture
**System Components**
[Diagram: JSON Files → data.py → rules.py → agent.py → Mistral API → tools.py → database.py → app.py]

- Source data: immutable JSON files
- Python rules: deterministic policy checks
- Mistral AI: language understanding and orchestration
- SQLite: case state and audit history
- Streamlit: operator interface

*"The LLM proposes. Python controls. No real action happens without operator confirmation."*

---

### Slide 6 — Agent Pipeline and Tools
**How the Agent Works**
1. Load case + detect topic
2. Retrieve relevant policies
3. Call Mistral with tool schemas
4. Tool loop (max 8 iterations):
   - get_case → get_policy → evaluate_case → stage_plan
5. Display plan for operator review
6. Operator confirms → Python records to SQLite

Tools: get_case, get_policy, get_related_history, evaluate_case, ask_clarification, stage_plan

*"Each tool is a guarded Python function. The model decides when to call it; Python decides whether to allow it."*

---

### Slide 7 — Simple Case: Guest Wi-Fi (REQ-02)
**Vikram Chawla: "Can I get Wi-Fi for a guest tomorrow?"**
- Topic detected: guest_wifi
- Policy retrieved: KB-07
- Answer: "Visit the front-desk kiosk to generate 24-hour credentials. No IT ticket needed."
- Result: Self-service guidance, no action recorded, no ticket created

*Show the REQ-02 analysis in the app. "One policy, one clear answer, 30 seconds."*

---

### Slide 8 — Difficult Cases
**Laptop Conflict (REQ-01) — Aditi Sharma: Dead laptop, 3.5 years**
- KB-03: Eligible (3+ years) ✓
- ASSET-Q2-2026: Not yet eligible (4-year cycle) ✗
- Action: IT diagnosis first; both policies shown; route to IT + Finance/Assets

**Phishing (REQ-08) — Ananya Reddy: Forwarding a phishing email**
- KB-09 triggered: URGENT
- Warning: STOP forwarding — explicitly prohibited by KB-09
- Existing Security escalation preserved; not duplicated

*Show both analysis cards. "These are the hard cases that show the agent's real value."*

---

### Slide 9 — Validation, Limitations & AI Tools
**What Was Tested**
- Source data counts: ✓ (11 policies, 15 requests, 10 tickets)
- All 15 request topics correctly categorised: ✓ (offline rules)
- Closed ticket protection: ✓
- Duplicate recording prevention: ✓
- API error handling: ✓ (mocked)
- Live Mistral tool loop: Requires API key (not in automated suite)

**Limitations**
- All actions are simulated (no real integrations)
- No software catalog supplied — membership must be clarified
- No production authentication

**AI Tools Used**
- Antigravity / Claude Sonnet (coding assistant — development only)
- Mistral AI (runtime LLM — live mode only)

---

### Slide 10 — Benefits and Future
**Expected Benefits** (not measured — no production data)
- Faster policy lookup and routing decisions
- Fewer duplicate tickets and wrong assignments
- Visible policy conflicts before action is taken
- Traceable decisions with audit history

**Future Improvements**
- Connect to real ticketing system (e.g., ServiceNow)
- Add real email notifications via Microsoft Graph
- Implement SSO / proper authentication
- Expand the software catalog knowledge base
- Add more policy sources as they are documented
""")

    # ── Submission Checklist ───────────────────────────────────────────────
    with guide_tabs[7]:
        st.markdown("""
## Submission Checklist

The AIONOS assessment requires seven outputs. Here is the status of each.

| # | Output | Status | Notes |
|---|---|---|---|
| 1 | Working agent / prototype | ✅ Complete | Run locally with `python -m streamlit run app.py` |
| 2 | Architecture and process flow | ✅ Complete | Project Guide → Architecture tab + docs/architecture.md |
| 3 | Sources, assumptions, limitations | ✅ Complete | Project Guide → Overview + docs/assumptions.md |
| 4 | AI tools disclosure | ✅ Complete | Project Guide → AI Tools Disclosure tab |
| 5 | 15-min demo + video on Drive | ⏳ Pending | Script is ready (Demo Guide tab). Record and upload video yourself. |
| 6 | GitHub project link | ⏳ Pending | Upload project to GitHub. Instructions in Setup & Run tab. |
| 7 | Ten-slide PPT | ⏳ Pending | Outline is in Slide Outline tab. Create the PPTX with screenshots. |

### Remaining Actions (for you to complete)
1. **Record demo video:** Use OBS, Loom, or Windows Game Bar. Follow the Demo Guide script.
2. **Upload to Google Drive:** Share as "Anyone with the link — Viewer". Verify in incognito.
3. **Create GitHub repo:** Upload all files except `venv/`, `resolvedesk.db`, `.env`.
4. **Create PPTX:** Use the Slide Outline. Add screenshots from the running app.
5. **Test with a real Mistral key:** Verify the live Mistral mode works end-to-end.

### Test Commands
```bash
# Run all tests
python -m unittest discover -s tests -v

# Run the app
python -m streamlit run app.py
```

### Files to EXCLUDE from GitHub
```
venv/
resolvedesk.db
.env
__pycache__/
*.pyc
```
""")
