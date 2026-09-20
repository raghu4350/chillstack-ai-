// src/components/Workspace/CaseSelector.jsx
export default function CaseSelector({ cases, currentIndex, onSelect }) {
  if (!cases.length) return null;
  const c = cases[currentIndex];
  const isActive = !c?.is_closed;

  return (
    <div style={{ marginBottom: 16 }}>
      {/* Top bar with label + nav */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: '0.65rem', fontWeight: 700, color: 'var(--accent-teal)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
            {isActive ? '● Active' : '○ Closed'} {c?.record_type === 'ticket' ? 'Ticket' : 'Request'}
          </span>
          <span style={{ color: 'var(--text-muted)', fontSize: '0.65rem' }}>•</span>
          <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-primary)' }}>{c?.id}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
            {currentIndex + 1} of {cases.length}
          </span>
          <button className="btn btn-ghost" style={{ padding: '4px 8px', fontSize: '0.7rem' }}
            disabled={currentIndex === 0}
            onClick={() => onSelect(currentIndex - 1)}>‹</button>
          <button className="btn btn-ghost" style={{ padding: '4px 8px', fontSize: '0.7rem' }}
            disabled={currentIndex === cases.length - 1}
            onClick={() => onSelect(currentIndex + 1)}>›</button>
        </div>
      </div>

      {/* Dropdown */}
      <div style={{ position: 'relative' }}>
        <select
          value={currentIndex}
          onChange={e => onSelect(Number(e.target.value))}
          style={{
            width: '100%', background: 'var(--bg-card)', border: '1px solid var(--border)',
            borderRadius: 10, padding: '12px 14px', color: 'var(--text-primary)',
            fontSize: '0.88rem', fontWeight: 600, fontFamily: 'Inter, sans-serif',
            cursor: 'pointer', appearance: 'none',
          }}
        >
          {cases.map((c, i) => (
            <option key={c.id} value={i} style={{ background: '#0d1f3c' }}>
              {c.id} — {c.employee || c.id} | {(c.request || c.issue_summary || '').slice(0, 55)}{c.is_closed ? ' [CLOSED]' : ''}
            </option>
          ))}
        </select>
        <span style={{ position: 'absolute', right: 14, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }}>⌄</span>
      </div>
    </div>
  );
}
