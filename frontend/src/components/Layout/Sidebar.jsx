// src/components/Layout/Sidebar.jsx
import { useEffect, useState } from 'react';
import { api } from '../../api/client';

const NAV = [
  { id: 'workspace', icon: '⚙️', label: 'Agent Workspace' },
  { id: 'cases',     icon: '📋', label: 'All Cases' },
  { id: 'policies',  icon: '📖', label: 'Policy Library' },
  { id: 'history',   icon: '📜', label: 'Action History' },
  { id: 'guide',     icon: '📚', label: 'Project Guide' },
];

export default function Sidebar({ active, onNavigate, offlineMode, onToggleOffline }) {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    api.getStats().then(setStats).catch(() => {});
  }, []);

  return (
    <aside style={{
      width: 'var(--sidebar-w)', background: 'var(--bg-secondary)',
      borderRight: '1px solid var(--border)',
      display: 'flex', flexDirection: 'column',
      flexShrink: 0, overflow: 'hidden',
    }}>
      {/* Section label */}
      <div style={{ padding: '16px 16px 8px' }}>
        <div className="section-label">Workspace</div>
      </div>

      {/* Navigation */}
      <nav style={{ padding: '0 8px', flex: 1 }}>
        {NAV.map(item => (
          <button
            key={item.id}
            onClick={() => onNavigate(item.id)}
            style={{
              width: '100%', display: 'flex', alignItems: 'center', gap: 10,
              padding: '9px 10px', borderRadius: 8, border: 'none', cursor: 'pointer',
              background: active === item.id ? 'rgba(0,212,170,0.12)' : 'transparent',
              color: active === item.id ? 'var(--accent-teal)' : 'var(--text-secondary)',
              fontSize: '0.82rem', fontWeight: active === item.id ? 600 : 400,
              fontFamily: 'Inter, sans-serif', marginBottom: 2,
              borderLeft: active === item.id ? '2px solid var(--accent-teal)' : '2px solid transparent',
              transition: 'all 0.15s ease', textAlign: 'left',
            }}
            onMouseEnter={e => { if (active !== item.id) { e.currentTarget.style.background = 'rgba(255,255,255,0.04)'; e.currentTarget.style.color = 'var(--text-primary)'; }}}
            onMouseLeave={e => { if (active !== item.id) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-secondary)'; }}}
          >
            <span style={{ fontSize: '0.95rem', minWidth: 18 }}>{item.icon}</span>
            {item.label}
          </button>
        ))}
      </nav>

      {/* Stats card */}
      <div style={{ padding: '0 12px 12px' }}>
        <div className="card" style={{ padding: '12px 14px' }}>
          <div className="section-label" style={{ marginBottom: 8 }}>System Status</div>
          {stats ? (
            <>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: 4 }}>
                <span style={{ color: 'var(--accent-teal)', fontWeight: 600 }}>{stats.total_policies}</span> Policies
                {' • '}
                <span style={{ color: 'var(--accent-teal)', fontWeight: 600 }}>{stats.total_requests}</span> Requests
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                <span style={{ color: 'var(--accent-teal)', fontWeight: 600 }}>{stats.total_tickets}</span> Tickets
                <span style={{ color: 'var(--text-muted)', marginLeft: 6 }}>
                  ({stats.active_tickets} active)
                </span>
              </div>
            </>
          ) : (
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Loading…</div>
          )}
        </div>

        {/* Offline toggle */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          marginTop: 10, padding: '8px 6px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            <span style={{ fontSize: '0.85rem' }}>🔌</span>
            <span style={{ fontSize: '0.78rem', color: offlineMode ? 'var(--warning)' : 'var(--text-secondary)' }}>
              Offline Mode
            </span>
          </div>
          <button
            onClick={onToggleOffline}
            style={{
              width: 36, height: 20, borderRadius: 10, border: 'none', cursor: 'pointer',
              background: offlineMode ? 'var(--warning)' : 'rgba(255,255,255,0.15)',
              position: 'relative', transition: 'background 0.2s',
            }}
          >
            <span style={{
              position: 'absolute', top: 2, left: offlineMode ? 17 : 2,
              width: 16, height: 16, borderRadius: '50%', background: '#fff',
              transition: 'left 0.2s', display: 'block',
            }} />
          </button>
        </div>
      </div>
    </aside>
  );
}
