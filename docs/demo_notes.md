# Demo Notes — ResolveDesk

## Pre-Demo Checklist
- [ ] App is running: `python -m streamlit run app.py`
- [ ] Browser is open at http://localhost:8501
- [ ] Offline mode is enabled (sidebar toggle) if no internet/key available
- [ ] All 5 tabs are visible
- [ ] Tests have been run and pass: `python -m unittest discover -s tests -v`

## Recommended Demo Sequence

### Case 1 — Simple: REQ-02 Guest Wi-Fi (Vikram Chawla)
- Shows: self-service guidance, KB-07 cited, no IT ticket
- Time: ~1 minute

### Case 2 — Conflict: REQ-01 Dead Laptop (Aditi Sharma)
- Shows: KB-03 AND ASSET-Q2-2026 both surfaced, conflict message, no auto-approval
- Time: ~2 minutes

### Case 3 — Security: REQ-08 Phishing (Ananya Reddy)
- Shows: urgent badge, stop-forwarding warning, existing escalation preserved
- Time: ~1 minute

### Case 4 — Vague: REQ-15 (Rahul Menon — "its not working")
- Shows: clarifying questions generated, topic = unknown
- Enter a clarification: "My VPN credentials expired"
- Re-analyse: topic changes to VPN, KB-02 cited
- Time: ~2 minutes

### Case 5 — Active Ticket: TK-1043 (Laptop pending fulfillment)
- Shows: approval preserved, fulfillment still pending, conflict surfaced
- Record an action → see it in Action History
- Time: ~2 minutes

### Closed Ticket Demo: TK-1042 or TK-1050
- Shows: read-only, no Record button, closed badge
- Time: ~30 seconds

## Key Points to Emphasise
1. "The LLM proposes — Python controls. No real action happens without my confirmation."
2. "Policy conflict: both rules shown, neither declared authoritative."
3. "Urgency does not override policy. REQ-10 asks for business justification."
4. "The audit trail shows every action, old status, new status, and policy cited."
5. "Offline mode is clearly labelled — it's not pretending to be AI."

## If the API is Slow or Fails
- Switch to offline mode using the sidebar toggle.
- Explain: "I've built an offline fallback using Python rules. In production,
  the LLM would be called via Mistral. Let me show you both modes."

## Defence Preparation
- Know the difference between KB-03 (IT policy) and ASSET-Q2-2026 (Finance/Assets policy).
- Know that TK-1043 is active (approved, pending fulfillment) not closed.
- Know that REQ-08 has an existing Security escalation that must be preserved.
- Know that REQ-10 (admin access) has no authorising policy — route to human reviewer.
