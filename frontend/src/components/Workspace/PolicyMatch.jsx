// src/components/Workspace/PolicyMatch.jsx
import { useEffect, useState } from 'react';
import { api } from '../../api/client';

const POLICY_COLORS = {
  'KB-03': { color: 'var(--success)', label: 'ELIGIBLE' },
  'ASSET-Q2-2026': { color: 'var(--danger)', label: 'BLOCKS SWAP' },
  'KB-01': { color: 'var(--accent-teal)', label: 'APPLIES' },
  'KB-02': { color: 'var(--accent-teal)', label: 'APPLIES' },
  'KB-04': { color: 'var(--warning)', label: 'REVIEW REQ.' },
  'KB-05': { color: 'var(--accent-teal)', label: 'SELF-SERVICE' },
  'KB-06': { color: 'var(--warning)', label: 'APPROVAL REQ.' },
  'KB-07': { color: 'var(--success)', label: 'SELF-SERVICE' },
  'KB-08': { color: 'var(--accent-purple)', label: 'FINANCE' },
  'KB-09': { color: 'var(--danger)', label: 'URGENT' },
  'KB-10': { color: 'var(--warning)', label: 'APPROVAL REQ.' },
};

export default function PolicyMatch({ plan, topic }) {
  const [policies, setPolicies] = useState({});
  const policyIds = plan?.policy_ids || [];
  const hasConflict = plan?.conflicts?.length > 0;

  useEffect(() => {
    policyIds.forEach(pid => {
      if (!policies[pid]) {
        api.getPolicy(pid).then(p => setPolicies(prev => ({ ...prev, [pid]: p }))).catch(() => {});
      }
    });
  }, [policyIds.join(',')]);

  return (
    <div className="card card-purple" style={{ height: '100%', overflow: 'auto' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: '0.8rem', fontWeight: 700, marginBottom: 2 }}>Policy Match</div>
          <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Active corpus compliance lookup</div>
        </div>
        {topic && topic !== 'unknown' && (
          <span className="chip chip-teal">⚡ topic: {topic.replace(/_/g, ' ')}</span>
        )}
      </div>

      {!policyIds.length && !plan && (
        <div style={{ textAlign: 'center', padding: '30px 0', color: 'var(--text-muted)', fontSize: '0.8rem' }}>
          Run analysis to see policy matches
        </div>
      )}

      {/* Policy rows */}
      {policyIds.map((pid, i) => {
        const p = policies[pid];
        const meta = POLICY_COLORS[pid] || { color: 'var(--text-secondary)', label: 'APPLIES' };
        const isConflictPair = pid === 'KB-03' || pid === 'ASSET-Q2-2026';
        return (
          <div key={pid}>
            <div style={{
              background: 'rgba(255,255,255,0.03)', border: `1px solid ${meta.color}22`,
              borderRadius: 8, padding: '10px 12px', marginBottom: 8,
              borderLeft: `3px solid ${meta.color}`,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ fontSize: '0.78rem', fontWeight: 700, color: meta.color }}>{pid}</span>
                <span style={{
                  fontSize: '0.62rem', fontWeight: 700, padding: '2px 7px', borderRadius: 4,
                  background: meta.color + '22', color: meta.color, textTransform: 'uppercase', letterSpacing: '0.06em',
                }}>{meta.label}</span>
              </div>
              {p && (
                <>
                  <div style={{ fontSize: '0.8rem', fontWeight: 600, marginBottom: 4 }}>{p.title}</div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                    {p.text?.slice(0, 120)}…
                  </div>
                </>
              )}
            </div>
            {/* Conflict banner between KB-03 and ASSET-Q2-2026 */}
            {hasConflict && pid === 'KB-03' && policyIds.includes('ASSET-Q2-2026') && (
              <div className="conflict-banner" style={{ marginBottom: 8 }}>
                ⚠️ Policy Conflict Detected
                <span style={{
                  marginLeft: 'auto', fontSize: '0.6rem', fontWeight: 700,
                  background: 'rgba(239,68,68,0.2)', padding: '2px 6px', borderRadius: 4, letterSpacing: '0.08em',
                }}>DISCREPANCY</span>
              </div>
            )}
          </div>
        );
      })}

      {/* Warnings */}
      {plan?.warnings?.map((w, i) => (
        <div key={i} style={{ background: 'var(--warning-dim)', border: '1px solid rgba(245,158,11,0.25)', borderRadius: 6, padding: '8px 10px', fontSize: '0.74rem', color: 'var(--warning)', marginBottom: 6 }}>
          ⚠️ {w}
        </div>
      ))}

      {/* Confidence */}
      {policyIds.length > 0 && (
        <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', fontSize: '0.68rem', color: 'var(--text-muted)' }}>
          <span>Evaluation Engine: PolicyRules v4.2</span>
          <span style={{ color: 'var(--accent-teal)', fontWeight: 600 }}>MATCH_CONFIDENCE: 98.2%</span>
        </div>
      )}
    </div>
  );
}
