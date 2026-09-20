// src/components/Workspace/AIAnalysis.jsx
export default function AIAnalysis({ plan, mode, loading, error, onRecord, onReanalyse, onClear, recorded, isClosed }) {
  if (loading) {
    return (
      <div className="card" style={{ background: 'linear-gradient(135deg, rgba(0,212,170,0.06), rgba(124,58,237,0.06))', border: '1px solid rgba(0,212,170,0.2)', padding: 30, textAlign: 'center' }}>
        <div className="spinner" style={{ margin: '0 auto 12px' }} />
        <div style={{ color: 'var(--accent-teal)', fontSize: '0.85rem', fontWeight: 600 }}>AI Analysing Case…</div>
        <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', marginTop: 4 }}>Calling Groq API · Applying policy rules</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card card-danger" style={{ padding: 20 }}>
        <div style={{ fontWeight: 700, marginBottom: 8, color: 'var(--danger)' }}>⚠ Analysis Error</div>
        <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>{error}</div>
        <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
          <button className="btn btn-ghost" onClick={onReanalyse}>🔄 Retry (Groq)</button>
          <button className="btn btn-ghost" onClick={() => onReanalyse(true)}>⚡ Try Offline Mode</button>
        </div>
      </div>
    );
  }

  if (!plan) {
    return (
      <div className="card" style={{ background: 'linear-gradient(135deg, rgba(0,212,170,0.04), rgba(124,58,237,0.04))', border: '1px solid rgba(0,212,170,0.12)', padding: 30, textAlign: 'center' }}>
        <div style={{ fontSize: '1.5rem', marginBottom: 10 }}>🤖</div>
        <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: 16 }}>
          Click <strong style={{ color: 'var(--accent-teal)' }}>Analyse Request</strong> to run AI analysis on this case
        </div>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
          {!isClosed && <button className="btn btn-primary" onClick={() => onReanalyse(false)}>🔍 Analyse (Groq AI)</button>}
          {!isClosed && <button className="btn btn-ghost" onClick={() => onReanalyse(true)}>⚡ Analyse (Offline)</button>}
        </div>
      </div>
    );
  }

  const readiness = plan.missing_info?.length ? Math.max(20, 95 - plan.missing_info.length * 15) : 88;

  return (
    <div style={{
      background: 'linear-gradient(135deg, rgba(0,212,170,0.06), rgba(124,58,237,0.06))',
      border: '1px solid rgba(0,212,170,0.25)', borderRadius: 12, padding: 20,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 34, height: 34, background: 'linear-gradient(135deg, var(--accent-teal), var(--accent-purple))', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1rem' }}>🤖</div>
          <div>
            <div style={{ fontWeight: 700, fontSize: '0.9rem' }}>AI Synthesis & Orchestration</div>
            <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>Deterministic policy reconciliation plan</div>
          </div>
          {mode === 'offline' && <span className="badge badge-warning">⚡ Offline Rules</span>}
          {mode === 'groq' && <span className="badge badge-teal">🤖 Groq AI</span>}
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          {plan.topic && <span className="chip chip-teal">⚡ {plan.topic.replace(/_/g,' ')}</span>}
          {plan.proposed_route && <span className="chip chip-purple">↗ Route: {plan.proposed_route}</span>}
          {plan.is_urgent && <span className="chip" style={{ background: 'var(--danger-dim)', color: 'var(--danger)', border: '1px solid rgba(239,68,68,0.3)' }}>🚨 Urgent</span>}
          {!plan.is_urgent && <span className="chip">Urgent: No</span>}
          <span className="chip chip-teal">✓ Confidence: {readiness}%</span>
        </div>
      </div>

      {/* Two-column body */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: 16, marginBottom: 16 }}>
        {/* Left: Plan */}
        <div>
          <div className="section-label">⊕ Proposed Action Plan</div>
          <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.65, marginBottom: 14 }}>
            {plan.proposed_action || plan.summary || 'No action proposed.'}
            {plan.conflicts?.length > 0 && (
              <span> Policy conflict: <span style={{ color: 'var(--accent-teal)', fontWeight: 600 }}>
                {plan.conflicts[0].slice(0, 100)}…
              </span></span>
            )}
          </div>

          {/* Employee explanation */}
          <div className="section-label">📨 Draft Employee Explanation (Pending Dispatch)</div>
          <div className="quote-box">
            "{plan.employee_explanation || 'No explanation generated.'}"
          </div>
        </div>

        {/* Right: Missing info */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <div className="section-label" style={{ marginBottom: 0 }}>Missing Information</div>
            {plan.missing_info?.length > 0 && (
              <span style={{ fontSize: '0.65rem', fontWeight: 700, color: 'var(--danger)', background: 'var(--danger-dim)', padding: '2px 6px', borderRadius: 4 }}>
                {plan.missing_info.length} PENDING
              </span>
            )}
          </div>
          {plan.missing_info?.length > 0 ? (
            plan.missing_info.map((m, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border)', borderRadius: 7, padding: '8px 10px', marginBottom: 6 }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>❓ {m.slice(0,55)}</span>
                <span style={{ color: 'var(--accent-teal)', fontSize: '1rem', cursor: 'pointer' }}>⊕</span>
              </div>
            ))
          ) : (
            <div style={{ fontSize: '0.75rem', color: 'var(--success)', padding: '8px 0' }}>✓ All required info present</div>
          )}

          {/* Questions for employee */}
          {plan.questions_for_employee?.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div className="section-label">Questions</div>
              {plan.questions_for_employee.map((q, i) => (
                <div key={i} style={{ fontSize: '0.73rem', color: 'var(--text-muted)', marginBottom: 4 }}>• {q}</div>
              ))}
            </div>
          )}

          {/* Resolution readiness */}
          <div style={{ marginTop: 14 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Resolution Readiness</span>
              <span style={{ fontSize: '0.7rem', color: 'var(--accent-teal)', fontWeight: 600 }}>{readiness}%</span>
            </div>
            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${readiness}%` }} />
            </div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: 14, borderTop: '1px solid var(--border)' }}>
        <span className="badge badge-purple">⚙️ SIMULATED — No real action taken</span>
        <div style={{ display: 'flex', gap: 8 }}>
          {!isClosed && (
            <button className="btn btn-ghost" onClick={onClear}>🔄 Re-analyse</button>
          )}
          {!isClosed && !plan.closed_history_only && (
            <button
              className="btn btn-primary"
              onClick={onRecord}
              disabled={recorded || isClosed}
            >
              {recorded ? '✅ Recorded' : '⊕ Record Local Action'}
            </button>
          )}
        </div>
      </div>

      {recorded && (
        <div style={{ marginTop: 10, padding: '8px 12px', background: 'var(--success-dim)', border: '1px solid rgba(34,197,94,0.3)', borderRadius: 8, fontSize: '0.78rem', color: 'var(--success)' }}>
          ✅ Action recorded to audit log. See Action History tab.
        </div>
      )}
    </div>
  );
}
