// src/components/PolicyLibrary/PolicyLibrary.jsx
import { useEffect, useState } from 'react';
import { api } from '../../api/client';

const POLICY_ICONS = { 'KB-01':'🔑','KB-02':'🔒','KB-03':'💻','KB-04':'⚙️','KB-05':'🖨️','KB-06':'📧','KB-07':'📶','KB-08':'💰','KB-09':'🚨','KB-10':'🏠','ASSET-Q2-2026':'📦' };

export default function PolicyLibrary() {
  const [policies, setPolicies] = useState([]);
  const [expanded, setExpanded] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getPolicies().then(d => { setPolicies(d.policies || []); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  return (
    <div style={{ padding: '20px 24px', overflow: 'auto', height: '100%' }}>
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ fontSize: '1.2rem', fontWeight: 700, marginBottom: 4 }}>📖 Policy Library</h2>
        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
          All {policies.length} source policies from Assignment 2 Data Pack. Displayed verbatim.
        </div>
      </div>

      {/* Conflict warning */}
      <div className="conflict-banner" style={{ marginBottom: 20, fontSize: '0.78rem', lineHeight: 1.5 }}>
        ⚠️ <div>
          <strong>Laptop Policy Conflict:</strong> KB-03 sets a <strong>3-year</strong> replacement threshold.
          ASSET-Q2-2026 sets a <strong>4-year</strong> refresh cycle.
          No precedence rule is supplied. Both are shown for every laptop case.
        </div>
      </div>

      {loading && <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>Loading policies…</div>}

      {policies.map(p => {
        const isOpen = expanded === p.id;
        const hasConflict = p.conflict_note;
        return (
          <div key={p.id} className="card" style={{ marginBottom: 10, border: `1px solid ${hasConflict ? 'rgba(239,68,68,0.3)' : 'var(--border)'}` }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer' }}
              onClick={() => setExpanded(isOpen ? null : p.id)}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontSize: '1.2rem' }}>{POLICY_ICONS[p.id] || '📋'}</span>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontWeight: 700, color: 'var(--accent-teal)', fontSize: '0.82rem' }}>{p.id}</span>
                    <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>{p.title}</span>
                    {hasConflict && <span className="badge badge-danger">⚠️ CONFLICT</span>}
                    {p.urgent && <span className="badge badge-danger">🚨 URGENT</span>}
                  </div>
                  <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                    Owner: {p.owner} · Approval: {typeof p.approval_required === 'boolean' ? (p.approval_required ? 'Required' : 'Not required') : p.approval_required}
                  </div>
                </div>
              </div>
              <span style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>{isOpen ? '▲' : '▼'}</span>
            </div>

            {isOpen && (
              <div style={{ marginTop: 14, paddingTop: 14, borderTop: '1px solid var(--border)' }}>
                <div style={{ fontSize: '0.83rem', color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: 10 }}>{p.text}</div>
                {hasConflict && (
                  <div className="conflict-banner" style={{ fontSize: '0.76rem', lineHeight: 1.5 }}>
                    ⚠️ {p.conflict_note}
                  </div>
                )}
                {p.limits && (
                  <div style={{ marginTop: 10, fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    <strong style={{ color: 'var(--text-secondary)' }}>Limits:</strong> Default {p.limits.default_gb}GB · Max {p.limits.max_gb}GB
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
