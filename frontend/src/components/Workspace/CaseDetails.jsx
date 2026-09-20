// src/components/Workspace/CaseDetails.jsx
function getInitials(name) {
  if (!name) return '??';
  return name.split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();
}
function avatarColor(name) {
  const colors = ['#00d4aa','#7c3aed','#f59e0b','#ef4444','#3b82f6','#ec4899'];
  let h = 0; for (let c of (name||'')) h = c.charCodeAt(0) + h * 31;
  return colors[Math.abs(h) % colors.length];
}

export default function CaseDetails({ caseData, dbState }) {
  if (!caseData) return null;
  const { case: c, clarifications = [] } = caseData;
  const status = c.initial_action || c.source_status || 'Not started';
  const isClosed = c.is_closed;
  const currentStatus = dbState?.current_status || status;
  const accentColor = avatarColor(c.employee || c.id);

  const statusColor = (() => {
    if (isClosed) return 'var(--text-muted)';
    const sl = status.toLowerCase();
    if (sl.includes('urgent') || sl.includes('escalat') || sl.includes('security')) return 'var(--danger)';
    if (sl.includes('progress') || sl.includes('investigating') || sl.includes('waiting')) return 'var(--warning)';
    return 'var(--text-muted)';
  })();

  return (
    <div className="card card-teal" style={{ height: '100%', overflow: 'auto' }}>
      {/* Card header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: 2 }}>Case Details</div>
          <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Originating employee incident intake</div>
        </div>
        <span className={`badge ${isClosed ? 'badge-muted' : 'badge-warning'}`}>{isClosed ? 'CLOSED' : status.slice(0, 22)}</span>
      </div>

      {/* Employee row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
        <div className="avatar" style={{ background: accentColor + '22', color: accentColor, border: `1.5px solid ${accentColor}44` }}>
          {getInitials(c.employee)}
        </div>
        <div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Employee</div>
          <div style={{ fontWeight: 600, fontSize: '0.88rem' }}>{c.employee || 'Unknown'}</div>
        </div>
        <div style={{ marginLeft: 'auto' }}>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Date Opened</div>
          <div style={{ fontWeight: 600, fontSize: '0.82rem' }}>
            📅 {c.opened ? new Date(c.opened).toLocaleDateString('en-GB', {day:'2-digit',month:'short',year:'numeric'}) : 'N/A'}
          </div>
        </div>
      </div>

      {/* Email */}
      {c.email && c.email !== 'Not supplied' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10, fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
          <span>@</span>
          <span>{c.email}</span>
        </div>
      )}

      {/* Tags */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 12 }}>
        {caseData.topic && caseData.topic !== 'unknown' && (
          <span className="chip chip-teal">⚡ {caseData.topic.replace(/_/g,' ')}</span>
        )}
        <span className="chip">{c.record_type === 'ticket' ? '🎫 Ticket' : '📨 Request'}</span>
        {c.source && <span className="chip">📄 {c.source}</span>}
        {dbState && <span className="chip chip-purple">v{dbState.version}</span>}
      </div>

      {/* Request / issue */}
      <div className="section-label">Reported Issue</div>
      <div className="quote-box" style={{ marginBottom: 12 }}>
        "{c.request || c.issue_summary || 'No description provided.'}"
      </div>

      {/* DB status */}
      {dbState && (
        <div style={{ background: 'rgba(0,212,170,0.06)', border: '1px solid rgba(0,212,170,0.15)', borderRadius: 6, padding: '8px 10px', marginBottom: 10 }}>
          <div style={{ fontSize: '0.68rem', color: 'var(--accent-teal)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>Current App Status</div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-primary)' }}>{currentStatus}</div>
        </div>
      )}

      {/* Clarifications */}
      {clarifications.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <div className="section-label">Clarifications ({clarifications.length})</div>
          {clarifications.slice(-2).map(cl => (
            <div key={cl.id} style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', padding: '6px 8px', background: 'rgba(255,255,255,0.03)', borderRadius: 6, marginBottom: 4 }}>
              <span style={{ color: 'var(--text-muted)', marginRight: 4 }}>[{cl.submitted_at?.slice(0,10)}]</span>
              {cl.clarification}
            </div>
          ))}
        </div>
      )}

      {/* Bottom meta */}
      <div style={{ display: 'flex', gap: 16, marginTop: 12, paddingTop: 10, borderTop: '1px solid var(--border)' }}>
        <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
          <span style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>ID: </span>{c.id}
        </div>
        <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
          <span style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>Status: </span>
          <span style={{ color: statusColor }}>{status}</span>
        </div>
      </div>
    </div>
  );
}
