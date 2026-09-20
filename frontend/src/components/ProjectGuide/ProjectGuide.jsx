// src/components/ProjectGuide/ProjectGuide.jsx
export default function ProjectGuide() {
  return (
    <div style={{ padding: '20px 24px', overflow: 'auto', height: '100%', maxWidth: 820 }}>
      <h2 style={{ fontSize: '1.2rem', fontWeight: 700, marginBottom: 4 }}>?? Project Guide</h2>
      <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: 24 }}>ResolveDesk — AIONOS Assignment 2 · Chillstack</div>

      {[
        { title: '??? Architecture', content: `ResolveDesk uses a 3-layer architecture:
• React + Vite frontend (port 5173) — premium dark UI
• FastAPI backend (port 8000) — REST API wrapping all Python modules
• resolvedesk/ Python package — unchanged business logic

All business logic (agent.py, rules.py, tools.py, database.py) is in the resolvedesk/ package and unchanged. The FastAPI backend exposes it as REST API endpoints.` },
        { title: '?? Key Policies', content: `KB-01: Password Reset — self-service portal or IT unlock after 5 failed attempts
KB-02: VPN Access — auto for full-time; manager approval for contractors
KB-03: Laptop Replacement — 3-year threshold (CONFLICT with ASSET-Q2-2026)
KB-04: Software — catalog self-install; non-catalog needs IT Security review
KB-05: Printer — check queue/spooler first; log ticket with asset tag if persists
KB-06: Mailbox — 25GB default; 50GB hard cap; >25GB needs manager approval
KB-07: Guest Wi-Fi — front-desk kiosk, 24hr validity, no IT ticket
KB-08: Expense Tool — Finance grants access; IT only helps if account exists
KB-09: Security Incident — report immediately; do NOT forward
KB-10: WFH Equipment — >3 days/week; manager + Finance approval required
ASSET-Q2-2026: 4-year refresh cycle (CONFLICT with KB-03 3-year rule)` },
        { title: '?? Policy Conflict', content: `LAPTOP POLICY CONFLICT:
KB-03 states 3-year replacement eligibility.
ASSET-Q2-2026 (updated Q2 2026) states 4-year refresh cycle.
No source-precedence rule is supplied.
Resolution: Always surface both policies, route to IT + Finance/Assets. Never auto-resolve.` },
        { title: '??? Safety Rules', content: `• No real actions: all email sends, unlocks, grants are SIMULATED
• API key safety: key in .env only, never in logs, DB, or code
• No eval/exec: tool arguments validated as typed Python data
• Bounded agent loop: max 8 tool iterations
• Duplicate recording prevention: DB status guard + React state flag
• Closed case protection: validate_plan() blocks recording` },
        { title: '?? Running the App', content: `Terminal 1 — FastAPI Backend:
  uvicorn backend.main:app --reload --port 8000
  
Terminal 2 — React Frontend:
  cd frontend && npm run dev
  
App: http://localhost:5173
API Docs: http://localhost:8000/docs

Original Streamlit (backup):
  python -m streamlit run app.py` },
        { title: '?? Tests', content: `python -m unittest discover -s tests -v

Tests verify (no API key needed):
• All 15 requests and 10 tickets load correctly
• Offline rules engine produces correct plans
• Policy conflict is detected for laptop cases
• Security cases are flagged urgent
• Closed cases cannot be actioned` },
      ].map(s => (
        <div key={s.title} className="card" style={{ marginBottom: 14 }}>
          <div style={{ fontWeight: 700, fontSize: '0.9rem', marginBottom: 10, color: 'var(--accent-teal)' }}>{s.title}</div>
          <pre style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.8rem', color: 'var(--text-secondary)', whiteSpace: 'pre-wrap', lineHeight: 1.7, margin: 0 }}>{s.content}</pre>
        </div>
      ))}
    </div>
  );
}
