// src/components/AllCases/AllCases.jsx
import { useEffect, useState } from 'react';
import { api } from '../../api/client';

function getInitials(name) {
  if (!name) return '??';
  return name.split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();
}

export default function AllCases({ onOpenCase }) {
  const [cases, setCases] = useState([]);
  const [filter, setFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getCases().then(d => { setCases(d.cases || []); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  const filtered = cases.filter(c => {
    if (typeFilter === 'request' && c.record_type !== 'request') return false;
    if (typeFilter === 'ticket' && c.record_type !== 'ticket') return false;
    if (statusFilter === 'active' && c.is_closed) return false;
    if (statusFilter === 'closed' && !c.is_closed) return false;
    if (filter) {
      const q = filter.toLowerCase();
      return c.id.toLowerCase().includes(q) || (c.employee||'').toLowerCase().includes(q) || (c.request||c.issue_summary||'').toLowerCase().includes(q);
    }
    return true;
  });

  return (
    <div style={{ padding: '20px 24px', overflow: 'auto', height: '100%' }}>
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ fontSize: '1.2rem', fontWeight: 700, marginBottom: 4 }}>📋 All Cases</h2>
        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
          {cases.length} source records · {cases.filter(c => !c.is_closed).length} active · {cases.filter(c => c.is_closed).length} closed
        </div>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <input className="input" placeholder="Search ID, employee, keyword…" value={filter} onChange={e => setFilter(e.target.value)} style={{ maxWidth: 280 }} />
        <select className="input" value={typeFilter} onChange={e => setTypeFilter(e.target.value)} style={{ maxWidth: 150 }}>
          <option value="all">All Types</option>
          <option value="request">Requests</option>
          <option value="ticket">Tickets</option>
        </select>
        <select className="input" value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{ maxWidth: 150 }}>
          <option value="all">All Statuses</option>
          <option value="active">Active Only</option>
          <option value="closed">Closed Only</option>
        </select>
      </div>

      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 12 }}>
        Showing <strong style={{ color: 'var(--text-primary)' }}>{filtered.length}</strong> of {cases.length} records
      </div>

      {loading && <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>Loading cases…</div>}

      {filtered.map(c => {
        const isClosed = c.is_closed;
        const status = c.initial_action || c.source_status || '?';
        return (
          <div key={c.id} className={`card ${isClosed ? '' : 'card-teal'}`} style={{ marginBottom: 10, cursor: 'pointer', transition: 'all 0.15s' }}
            onClick={() => onOpenCase && onOpenCase(c.id)}
            onMouseEnter={e => e.currentTarget.style.borderColor = isClosed ? 'var(--border-hover)' : 'var(--accent-teal)'}
            onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div className="avatar" style={{ background: isClosed ? 'rgba(255,255,255,0.06)' : 'rgba(0,212,170,0.12)', color: isClosed ? 'var(--text-muted)' : 'var(--accent-teal)', fontSize: '0.72rem', width: 34, height: 34 }}>
                {getInitials(c.employee)}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontWeight: 700, fontSize: '0.85rem', color: 'var(--text-primary)' }}>{c.id}</span>
                  <span className={`badge ${isClosed ? 'badge-muted' : 'badge-teal'}`}>{isClosed ? 'CLOSED' : 'ACTIVE'}</span>
                  <span className="badge badge-muted">{c.record_type}</span>
                  {c.db_state && <span className="badge badge-purple">Updated</span>}
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: 4 }}>
                  <strong style={{ color: 'var(--text-primary)' }}>{c.employee}</strong>
                  {c.email && c.email !== 'Not supplied' && <span style={{ color: 'var(--text-muted)', marginLeft: 6 }}>· {c.email}</span>}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {(c.request || c.issue_summary || '').slice(0, 110)}
                </div>
              </div>
              <div style={{ textAlign: 'right', flexShrink: 0 }}>
                <div style={{ fontSize: '0.72rem', color: isClosed ? 'var(--text-muted)' : 'var(--warning)', fontWeight: 600 }}>{status.slice(0, 30)}</div>
                {c.db_state && <div style={{ fontSize: '0.68rem', color: 'var(--accent-teal)', marginTop: 2 }}>{c.db_state.current_status?.slice(0,25)}</div>}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
