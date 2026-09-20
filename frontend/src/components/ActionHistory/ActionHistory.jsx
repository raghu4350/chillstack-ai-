// src/components/ActionHistory/ActionHistory.jsx
import { useEffect, useState } from 'react';
import { api } from '../../api/client';

export default function ActionHistory() {
  const [records, setRecords] = useState([]);
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(true);

  const load = () => {
    api.getAudit().then(d => { setRecords(d.records || []); setLoading(false); }).catch(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  const filtered = filter ? records.filter(r => r.case_id?.includes(filter.toUpperCase())) : records;

  const handleExport = async () => {
    const d = await api.getAudit();
    const blob = new Blob([JSON.stringify(d.records, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'resolvedesk_audit.json'; a.click();
  };

  return (
    <div style={{ padding: '20px 24px', overflow: 'auto', height: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 700, marginBottom: 4 }}>📜 Action History</h2>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>Append-only audit log. API keys are never stored here.</div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-ghost" onClick={load}>🔄 Refresh</button>
          <button className="btn btn-ghost" onClick={handleExport}>⬇️ Export JSON</button>
        </div>
      </div>

      <input className="input" placeholder="Filter by Case ID (e.g. REQ-01)" value={filter} onChange={e => setFilter(e.target.value)} style={{ maxWidth: 300, marginBottom: 16 }} />

      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 12 }}>
        <strong style={{ color: 'var(--text-primary)' }}>{filtered.length}</strong> records {filter ? '(filtered)' : '(all time)'}
      </div>

      {loading && <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>Loading audit log…</div>}

      {!loading && !filtered.length && (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
          No audit records yet. Analyse a case and record an action.
        </div>
      )}

      {filtered.map(r => {
        const isUrgent = r.action_type?.includes('security');
        return (
          <div key={r.id} className={`card ${isUrgent ? 'card-danger' : 'card-teal'}`} style={{ marginBottom: 10 }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontWeight: 700, color: 'var(--accent-teal)', fontSize: '0.85rem' }}>{r.case_id}</span>
                <code style={{ fontSize: '0.68rem', background: 'rgba(255,255,255,0.08)', padding: '2px 6px', borderRadius: 4, color: 'var(--text-secondary)' }}>{r.action_type}</code>
                {r.is_simulation && <span className="badge badge-purple">⚙️ SIMULATED</span>}
              </div>
              <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', flexShrink: 0, marginLeft: 8 }}>{r.timestamp}</span>
            </div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.5, marginBottom: 6 }}>
              {r.description}
            </div>
            {r.old_status && r.new_status && (
              <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                Status: <span style={{ color: 'var(--warning)' }}>{r.old_status}</span>
                {' → '}
                <span style={{ color: 'var(--success)' }}>{r.new_status}</span>
              </div>
            )}
            {r.evidence_ids?.length > 0 && (
              <div style={{ marginTop: 6, fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                Evidence: {r.evidence_ids.map(e => <span key={e} className="chip chip-teal" style={{ marginRight: 4, fontSize: '0.65rem', padding: '1px 6px' }}>{e}</span>)}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
