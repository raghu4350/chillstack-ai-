// src/components/Layout/Header.jsx
import { useEffect, useState } from 'react';
import { api } from '../../api/client';

export default function Header({ offlineMode }) {
  const [connected, setConnected] = useState(false);
  const [groqModel, setGroqModel] = useState('');

  useEffect(() => {
    api.health().then(() => setConnected(true)).catch(() => setConnected(false));
    api.getStats().then(d => setGroqModel(d.groq_model || '')).catch(() => {});
  }, []);

  return (
    <header style={{
      height: 'var(--header-h)', background: 'var(--bg-secondary)',
      borderBottom: '1px solid var(--border)',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '0 20px', flexShrink: 0, zIndex: 100,
    }}>
      {/* Logo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{
          width: 32, height: 32, background: 'var(--accent-teal)',
          borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: '1rem',
        }}>???</div>
        <div>
          <div style={{ fontWeight: 700, fontSize: '1rem', letterSpacing: '-0.01em' }}>ResolveDesk</div>
          <div style={{ fontSize: '0.62rem', color: 'var(--accent-teal)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
            Chillstack — AI Service Desk
          </div>
        </div>
      </div>

      {/* Right badges */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        {offlineMode ? (
          <span className="badge badge-warning">? Offline Mode</span>
        ) : (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 7,
            background: connected ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
            border: `1px solid ${connected ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
            borderRadius: 20, padding: '5px 12px', fontSize: '0.75rem', fontWeight: 600,
          }}>
            <span className="pulse" style={{ color: connected ? 'var(--success)' : 'var(--danger)', fontSize: '0.6rem' }}>?</span>
            <span style={{ color: connected ? 'var(--success)' : 'var(--danger)' }}>
              {connected ? 'Groq AI Connected' : 'Backend Offline'}
            </span>
          </div>
        )}
        <div style={{
          width: 32, height: 32, borderRadius: '50%',
          background: 'linear-gradient(135deg, var(--accent-teal), var(--accent-purple))',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: '0.75rem', fontWeight: 700, color: '#fff', cursor: 'pointer',
        }}>OP</div>
      </div>
    </header>
  );
}
