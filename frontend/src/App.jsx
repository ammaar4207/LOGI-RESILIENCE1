import React, { useEffect, useState } from 'react';
import Map3D from './components/Map3D';
import Sidebar from './components/Sidebar';
import NotificationToast from './components/NotificationToast';
import { useStore } from './store';
import { useRiskStream } from './hooks/useRiskStream';
import './styles/app.css';

const App = () => {
  const [rebookingState, setRebookingState] = useState('idle'); // idle, loading, success
  const [bookingData, setBookingData] = useState(null);

  const { 
    wsStatus, meta, activeTab, setActiveTab, setOptimizationMode, optimizationMode, 
    metrics, setMetrics, updateMeta, setDisruptions,
    forecastDays, setForecastDays, forecastData, setForecastData,
    agentProposal, setAgentProposal, setActiveSimulationPath
  } = useStore();
  const livePayload = useRiskStream();

  // Fetch forecast data when slider changes
  useEffect(() => {
    if (forecastDays > 0) {
      const apiUrl = import.meta.env.VITE_API_URL ?? '';
      fetch(`${apiUrl}/api/v1/analytics/forecast?days=${forecastDays}`)
        .then(r => r.json())
        .then(d => {
          if (d.status === 'FORECAST') {
            setForecastData(d);
          }
        })
        .catch(console.error);
    } else {
      setForecastData(null);
    }
  }, [forecastDays, setForecastData]);

  // Sync live payload ONLY if not forecasting
  useEffect(() => {
    if (livePayload && forecastDays === 0) {
      setMetrics(livePayload.metrics || []);
      if (livePayload.disruptions) {
        setDisruptions(livePayload.disruptions);
      }
      if (livePayload.camps) {
        useStore.getState().setCamps(livePayload.camps);
      }
      updateMeta({
        status: livePayload.status,
        updated: new Date(livePayload.timestamp).toLocaleTimeString(),
        nodes: livePayload.network_density?.nodes || 0,
        edges: livePayload.network_density?.edges || 0,
        resilience: livePayload.global_resilience_index,
      });
    } else if (forecastData && forecastDays > 0) {
      // If forecasting, override the metrics with the forecasted metrics
      setMetrics(forecastData.metrics || []);
      if (forecastData.disruptions) {
        setDisruptions(forecastData.disruptions);
      }
      if (forecastData.camps) {
        useStore.getState().setCamps(forecastData.camps);
      }
      updateMeta({
        status: `FORECAST: DAY ${forecastDays}`,
        updated: `Projected +${forecastDays} Days`,
        resilience: forecastData.global_resilience_index,
      });
    }
  }, [livePayload, forecastData, forecastDays, setMetrics, updateMeta, setDisruptions]);

  return (
    <div className="app-container">
      {/* ── Global Notifications ───────────────────────────────────────────── */}
      <NotificationToast />

      {/* ── Header ───────────────────────────────────────────────────────── */}
      <header className="app-header">
        <div className="brand-section">
          <div className="brand-logo">L</div>
          <div>
            <h1 className="brand-title">LOGI-RESILIENCE</h1>
            <div className="brand-subtitle">AI Maritime Network Analytics</div>
          </div>
        </div>

        {/* ── Tab Navigation ───────────────────────────────────────────────── */}
        <div className="tab-nav">
          <button className={`tab-btn ${activeTab === 'map' ? 'active-map' : ''}`} onClick={() => setActiveTab('map')}>Global Map</button>
          <button className={`tab-btn ${activeTab === 'network' ? 'active-network' : ''}`} onClick={() => setActiveTab('network')}>Network Grid</button>
          <button className={`tab-btn ${activeTab === 'carbon' ? 'active-carbon' : ''}`} onClick={() => setActiveTab('carbon')}>Carbon Dashboard</button>
          <button className={`tab-btn ${activeTab === 'timeline' ? 'active-timeline' : ''}`} onClick={() => setActiveTab('timeline')}>Alerts Timeline</button>
          <button className={`tab-btn ${activeTab === 'bookings' ? 'active-bookings' : ''}`} onClick={() => setActiveTab('bookings')}>Active Bookings</button>
        </div>

        {/* ── Strategy Toggles (Only visible when map is active) ──────────── */}
        {activeTab === 'map' ? (
          <div className="strategy-toggle-container">
            <button className={`strategy-btn ${optimizationMode === 'resilience' ? 'active-resilience' : ''}`} onClick={() => setOptimizationMode('resilience')}>Resilience</button>
            <button className={`strategy-btn ${optimizationMode === 'sustainability' ? 'active-sustainability' : ''}`} onClick={() => setOptimizationMode('sustainability')}>Eco-Routing</button>
            <button className={`strategy-btn ${optimizationMode === 'financial' ? 'active-financial' : ''}`} onClick={() => setOptimizationMode('financial')}>Financial</button>
            <button className={`strategy-btn ${optimizationMode === 'essential' ? 'active-essential' : ''}`} onClick={() => setOptimizationMode('essential')}>Essential Cargo</button>
          </div>
        ) : (
          <div style={{ width: 300 }}></div> // Spacer for layout balance
        )}

        {/* ── Telemetry Stats ────────────────────────────────────────────── */}
        <div className="meta-stats-container" style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 12px', background: 'rgba(255,255,255,0.05)', borderRadius: 20 }}>
            <div className={`status-dot status-${wsStatus}`} />
            <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)' }}>{wsStatus}</span>
          </div>
          <div className="meta-stat-item">
            <span>RESILIENCE</span>
            <div className="stat-value resilience-val">{meta.resilience !== null ? meta.resilience : '--'}/100</div>
          </div>
          <div className="meta-stat-item">
            <span>LANE ACTIVITY</span>
            <div className="stat-value">{meta.edges}</div>
          </div>
          <div className="meta-stat-item" style={{ textAlign: 'right' }}>
            <span>LATEST SYNC</span>
            <div style={{ color: 'var(--text-secondary)', fontWeight: 600 }}>{meta.updated}</div>
          </div>
        </div>
      </header>

      {/* ── Workspace ────────────────────────────────────────────────────── */}
      <main className="workspace-splitter">
        {/* Map takes full remaining space when active, otherwise hidden */}
        <div style={{ display: activeTab === 'map' ? 'block' : 'none', flex: 1, position: 'relative' }}>
          <Map3D metrics={metrics} optimizationMode={optimizationMode} />
          
          {/* Timeline Slider Overlay */}
          <div style={{ 
            position: 'absolute', bottom: 40, left: '50%', transform: 'translateX(-50%)', 
            width: '60%', background: 'rgba(15, 23, 42, 0.85)', backdropFilter: 'blur(12px)',
            border: '1px solid #334155', borderRadius: 12, padding: '16px 24px', zIndex: 10,
            display: 'flex', flexDirection: 'column', gap: 8
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: 1 }}>
                PREDICTIVE FORECASTING
              </span>
              <span style={{ fontSize: 14, fontWeight: 800, color: forecastDays > 0 ? '#f59e0b' : '#10b981' }}>
                {forecastDays === 0 ? 'LIVE STREAM' : `DAY +${forecastDays}`}
              </span>
            </div>
            <input 
              type="range" 
              min="0" max="14" 
              value={forecastDays} 
              onChange={(e) => setForecastDays(parseInt(e.target.value))}
              style={{ width: '100%', cursor: 'pointer', accentColor: forecastDays > 0 ? '#f59e0b' : '#10b981' }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text-muted)' }}>
              <span>Live (0)</span>
              <span>1 Week (+7)</span>
              <span>2 Weeks (+14)</span>
            </div>
          </div>
        </div>
        
        {/* Full-width panel viewport for non-map tabs */}
        {activeTab !== 'map' && (
          <div className="panel-viewport">
            <Sidebar />
          </div>
        )}

        {/* Sidebar viewport for map controls (only visible on map tab) */}
        {activeTab === 'map' && (
          <Sidebar />
        )}
      </main>

      {/* ── Agent Proposal Modal ───────────────────────────────────────────── */}
      {agentProposal && (
        <div style={{
          position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
          background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)', zIndex: 1000,
          display: 'flex', alignItems: 'center', justifyContent: 'center'
        }}>
          <div style={{
            background: 'var(--panel-bg)', border: '1px solid #334155', borderRadius: 12,
            padding: 32, maxWidth: 600, width: '90%', color: 'var(--text-primary)'
          }}>
            {rebookingState === 'idle' && (
              <>
                <h2 style={{ margin: '0 0 16px', color: optimizationMode === 'essential' ? '#fbbf24' : '#38bdf8' }}>
                  {optimizationMode === 'essential' ? '⚠️ Dual-Mandate Mitigation' : '⚠️ Agent Mitigation Proposal'}
                </h2>
                <p style={{ margin: '0 0 16px', color: 'var(--text-secondary)' }}>
                  A critical disruption has been detected on <strong>{agentProposal.lane_id}</strong>.
                </p>
                <div style={{ background: 'rgba(0,0,0,0.3)', padding: 16, borderRadius: 8, marginBottom: 16 }}>
                  <p style={{ margin: 0, fontStyle: 'italic', color: optimizationMode === 'essential' ? '#ef4444' : '#fbbf24' }}>
                    "{optimizationMode === 'essential' && agentProposal.summary_essential ? agentProposal.summary_essential : agentProposal.summary}"
                  </p>
                </div>
                <p style={{ margin: '0 0 24px', fontSize: 14 }}>
                  <strong>Alternative Route:</strong> {agentProposal.alternative_route.join(' ➔ ')}<br/>
                  {optimizationMode !== 'essential' && (
                    <><strong>Estimated Carbon Tax Impact:</strong> +${agentProposal.cost_impact.toLocaleString()}<br/></>
                  )}
                  {optimizationMode === 'essential' && (
                    <strong style={{ color: '#ef4444' }}>
                      Expedited Humanitarian Cost (incl. Carbon Offset): +${(agentProposal.cost_impact * 1.5).toLocaleString()}
                    </strong>
                  )}
                </p>
                <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
                  <button 
                    onClick={() => setAgentProposal(null)}
                    style={{ background: 'transparent', border: '1px solid #475569', color: '#cbd5e1', padding: '8px 16px', borderRadius: 6, cursor: 'pointer' }}
                  >
                    Reject
                  </button>
                  <button 
                    onClick={async () => {
                      setRebookingState('loading');
                      const apiUrl = import.meta.env.VITE_API_URL ?? '';
                      try {
                        const res = await fetch(`${apiUrl}/api/v1/simulations/approve_detour`, {
                          method: 'POST',
                          headers: { 
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${useStore.getState().token}`
                          },
                          body: JSON.stringify({
                            lane_id: agentProposal.lane_id,
                            alternative_lanes: agentProposal.alternative_lanes || [],
                            is_essential: optimizationMode === 'essential'
                          })
                        });
                        const data = await res.json();
                        setBookingData(data);
                        
                        setActiveSimulationPath({
                          path: agentProposal.alternative_route || [],
                          lanes: agentProposal.alternative_lanes || [],
                          total_distance_km: agentProposal.alternative_distance || 'Unknown',
                          mitigation_strategy: optimizationMode === 'essential' && agentProposal.summary_essential ? agentProposal.summary_essential : agentProposal.summary
                        });
                        setRebookingState('success');
                      } catch (err) {
                        console.error(err);
                        setRebookingState('idle');
                        setAgentProposal(null);
                      }
                    }}
                    style={{ background: '#38bdf8', border: 'none', color: '#0f172a', fontWeight: 'bold', padding: '8px 16px', borderRadius: 6, cursor: 'pointer' }}
                  >
                    Approve Detour
                  </button>
                </div>
              </>
            )}

            {rebookingState === 'loading' && (
              <div style={{ textAlign: 'center', padding: '40px 0' }}>
                <div className="spinner" style={{ margin: '0 auto 20px' }}></div>
                <h3 style={{ margin: '0 0 10px', color: '#38bdf8' }}>Negotiating with Carrier APIs...</h3>
                <p style={{ margin: 0, color: 'var(--text-secondary)' }}>Drafting Shipper Communications via LLM...</p>
              </div>
            )}

            {rebookingState === 'success' && bookingData && (
              <>
                <h2 style={{ margin: '0 0 16px', color: '#10b981' }}>
                  ✅ {optimizationMode === 'essential' ? 'Dual-Mandate Route Confirmed' : 'Re-booking Confirmed'}
                </h2>
                <div style={{ 
                  background: optimizationMode === 'essential' ? 'rgba(251, 191, 36, 0.1)' : 'rgba(16, 185, 129, 0.1)', 
                  border: `1px solid ${optimizationMode === 'essential' ? '#fbbf24' : '#10b981'}`, 
                  padding: 16, borderRadius: 8, marginBottom: 20 
                }}>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4 }}>
                    {optimizationMode === 'essential' ? 'Dual-Mandate Booking Ref' : 'Carrier Booking Reference'}
                  </div>
                  <div style={{ fontSize: 24, fontWeight: 'bold', color: optimizationMode === 'essential' ? '#fbbf24' : '#fff', letterSpacing: 2 }}>
                    {bookingData.booking_reference}
                  </div>
                </div>
                
                <h3 style={{ margin: '0 0 12px', fontSize: 14, color: 'var(--text-secondary)' }}>Generated Shipper Notification:</h3>
                <div style={{ background: '#0f172a', border: '1px solid #334155', padding: 16, borderRadius: 8, marginBottom: 24, fontSize: 13, lineHeight: 1.6, whiteSpace: 'pre-wrap', color: '#cbd5e1' }}>
                  {bookingData.shipper_email}
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <button 
                    onClick={() => {
                      setRebookingState('idle');
                      setBookingData(null);
                      setAgentProposal(null);
                    }}
                    style={{ background: '#10b981', border: 'none', color: '#fff', fontWeight: 'bold', padding: '8px 24px', borderRadius: 6, cursor: 'pointer' }}
                  >
                    Done
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default App;