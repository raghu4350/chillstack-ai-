// src/App.jsx
import { useEffect, useState } from 'react';
import Header from './components/Layout/Header';
import Sidebar from './components/Layout/Sidebar';
import CaseSelector from './components/Workspace/CaseSelector';
import CaseDetails from './components/Workspace/CaseDetails';
import PolicyMatch from './components/Workspace/PolicyMatch';
import AIAnalysis from './components/Workspace/AIAnalysis';
import AllCases from './components/AllCases/AllCases';
import PolicyLibrary from './components/PolicyLibrary/PolicyLibrary';
import ActionHistory from './components/ActionHistory/ActionHistory';
import ProjectGuide from './components/ProjectGuide/ProjectGuide';
import { api } from './api/client';

export default function App() {
  const [view, setView] = useState('workspace');
  const [offlineMode, setOfflineMode] = useState(false);

  // Cases
  const [cases, setCases] = useState([]);
  const [caseIndex, setCaseIndex] = useState(0);
  const [caseData, setCaseData] = useState(null);

  // Analysis state
  const [plan, setPlan] = useState(null);
  const [analyseMode, setAnalyseMode] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [recorded, setRecorded] = useState(false);

  // Clarification
  const [clarText, setClarText] = useState('');
  const [clarSaving, setClarSaving] = useState(false);

  // Load all cases on mount
  useEffect(() => {
    api.getCases().then(d => setCases(d.cases || [])).catch(() => {});
  }, []);

  // Load case detail when index changes
  useEffect(() => {
    if (!cases.length) return;
    const c = cases[caseIndex];
    setPlan(null); setError(null); setRecorded(false);
    api.getCase(c.id).then(setCaseData).catch(() => {});
  }, [caseIndex, cases]);

  const handleAnalyse = async (forceOffline = false) => {
    if (!caseData) return;
    setLoading(true); setError(null); setPlan(null); setRecorded(false);
    try {
      const useOffline = forceOffline || offlineMode;
      const fn = useOffline ? api.analyseCaseOffline : api.analyseCase;
      const result = await fn(caseData.case.id);
      if (result.success && result.plan) {
        setPlan(result.plan); setAnalyseMode(result.mode);
      } else {
        setError(result.error || 'Analysis returned no plan. Try offline mode.');
      }
    } catch (e) {
      setError(e.message || 'Failed to contact backend.');
    }
    setLoading(false);
  };

  const handleRecord = async () => {
    if (!plan || !caseData) return;
    try {
      await api.recordAction(caseData.case.id, {
        proposed_action: plan.proposed_action || plan.summary || '',
        proposed_status: plan.proposed_status || 'In progress',
        policy_ids: plan.policy_ids || [],
        topic: plan.topic || caseData.topic || '',
        mode: analyseMode || 'groq',
        summary: plan.summary || '',
      });
      setRecorded(true);
      // Refresh case data
      const fresh = await api.getCase(caseData.case.id);
      setCaseData(fresh);
    } catch (e) {
      setError(e.message || 'Failed to record action.');
    }
  };

  const handleClear = async () => {
    if (!caseData) return;
    await api.clearConversation(caseData.case.id).catch(() => {});
    setPlan(null); setError(null); setRecorded(false);
    handleAnalyse();
  };

  const handleAddClarification = async () => {
    if (!clarText.trim() || !caseData) return;
    setClarSaving(true);
    await api.addClarification(caseData.case.id, { clarification: clarText.trim() }).catch(() => {});
    const fresh = await api.getCase(caseData.case.id).catch(() => null);
    if (fresh) setCaseData(fresh);
    setClarText(''); setClarSaving(false);
  };

  const handleOpenCase = (caseId) => {
    const idx = cases.findIndex(c => c.id === caseId);
    if (idx >= 0) { setCaseIndex(idx); setView('workspace'); }
  };

  const isClosed = caseData?.is_closed || cases[caseIndex]?.is_closed || false;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <Header offlineMode={offlineMode} />
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <Sidebar
          active={view}
          onNavigate={setView}
          offlineMode={offlineMode}
          onToggleOffline={() => setOfflineMode(p => !p)}
        />

        {/* Main content */}
        <main style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>

          {/* AGENT WORKSPACE */}
          {view === 'workspace' && (
            <div style={{ flex: 1, overflow: 'auto', padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 14 }}>
              {/* Case selector */}
              <CaseSelector cases={cases} currentIndex={caseIndex} onSelect={idx => setCaseIndex(idx)} />

              {/* Two column: Case Details + Policy Match */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, minHeight: 0 }}>
                <CaseDetails caseData={caseData} dbState={caseData?.db_state} />
                <PolicyMatch plan={plan} topic={caseData?.topic} />
              </div>

              {/* Clarification form */}
              {caseData && !isClosed && (
                <div style={{ display: 'flex', gap: 8 }}>
                  <input
                    className="input"
                    placeholder="Add clarification or operator note…"
                    value={clarText}
                    onChange={e => setClarText(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleAddClarification()}
                  />
                  <button className="btn btn-ghost" onClick={handleAddClarification} disabled={clarSaving || !clarText.trim()}>
                    {clarSaving ? '…' : '+ Add Note'}
                  </button>
                  {!plan && !loading && (
                    <button className="btn btn-primary" onClick={() => handleAnalyse(offlineMode)}>
                      {offlineMode ? '⚡ Analyse (Offline)' : '🔍 Analyse (Groq)'}
                    </button>
                  )}
                </div>
              )}

              {/* AI Analysis card */}
              <AIAnalysis
                plan={plan}
                mode={analyseMode}
                loading={loading}
                error={error}
                onRecord={handleRecord}
                onReanalyse={handleAnalyse}
                onClear={handleClear}
                recorded={recorded}
                isClosed={isClosed}
              />
            </div>
          )}

          {view === 'cases' && <AllCases onOpenCase={handleOpenCase} />}
          {view === 'policies' && <PolicyLibrary />}
          {view === 'history' && <ActionHistory />}
          {view === 'guide' && <ProjectGuide />}
        </main>
      </div>
    </div>
  );
}
