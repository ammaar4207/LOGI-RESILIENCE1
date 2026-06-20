import React, { useState, useEffect } from 'react';
import { useStore } from '../store';
import NetworkHealthGrid from './NetworkHealthGrid';
import CarbonDashboard from './CarbonDashboard';
import AlertsTimeline from './AlertsTimeline';
import ActiveBookings from './ActiveBookings';

const apiUrl = import.meta.env.VITE_API_URL ?? '';

const PORTS = [
  { id: "SGSIN", name: "Singapore" },
  { id: "CNSHA", name: "Shanghai" },
  { id: "KRPUS", name: "Busan" },
  { id: "CNHKG", name: "Hong Kong" },
  { id: "CNNBO", name: "Ningbo-Zhoushan" },
  { id: "CNQIN", name: "Qingdao" },
  { id: "TWKHH", name: "Kaohsiung" },
  { id: "JPTYO", name: "Tokyo (Yokohama)" },
  { id: "MYPKG", name: "Port Klang (KL)" },
  { id: "PHMNI", name: "Manila" },
  { id: "LKCMB", name: "Colombo" },
  { id: "VNCPH", name: "Ho Chi Minh City" },
  { id: "INMUN", name: "Mumbai (JNPT)" },
  { id: "AEJEA", name: "Jebel Ali (Dubai)" },
  { id: "OMSLL", name: "Salalah (Oman)" },
  { id: "SADMM", name: "Dammam (Saudi)" },
  { id: "EGSUZ", name: "Suez Canal Zone" },
  { id: "SGSTR", name: "Strait of Malacca" },
  { id: "NLRTM", name: "Rotterdam" },
  { id: "DEHAM", name: "Hamburg" },
  { id: "BEANT", name: "Antwerp" },
  { id: "ESVLC", name: "Valencia" },
  { id: "GRPIR", name: "Piraeus (Athens)" },
  { id: "ITGOA", name: "Genoa" },
  { id: "USLAX", name: "Los Angeles" },
  { id: "USNYC", name: "New York (Newark)" },
  { id: "USHOH", name: "Houston" },
  { id: "BRSSZ", name: "Santos (Brazil)" },
  { id: "ZADUR", name: "Durban" },
  { id: "NGLOS", name: "Lagos (Apapa)" }
];

const Sidebar = () => {
  const { optimizationMode, setOptimizationMode, activeTab, activeSimulationPath, resetSimulation, role, disruptions, metrics } = useStore();
  const [targetEdge, setTargetEdge] = useState('CNSHA-USLAX');
  const [severity, setSeverity] = useState(0.8);
  const [disruptionType, setDisruptionType] = useState('hurricane');
  const [sourceNode, setSourceNode] = useState('CNSHA');
  const [targetNode, setTargetNode] = useState('USLAX');
  const [avoidEdgeId, setAvoidEdgeId] = useState('');
  const [loadingMsg, setLoadingMsg] = useState('');



  const handleInject = async () => {
    setLoadingMsg('Injecting disruption...');
    try {
      const payload = [{
        id: `disrup-${Date.now()}`,
        type: disruptionType,
        target: targetEdge,
        severity: severity
      }];

      const res = await fetch(`${apiUrl}/api/v1/simulations/disruptions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${useStore.getState().token}`
        },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        setTimeout(() => setLoadingMsg(''), 1000);
      } else {
        throw new Error('Failed to inject');
      }
    } catch (err) {
      alert('Error injecting disruption');
      setLoadingMsg('');
    }
  };

  const handleClearDisruptions = async () => {
    setLoadingMsg('Clearing disruptions...');
    try {
      const res = await fetch(`${apiUrl}/api/v1/simulations/disruptions`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${useStore.getState().token}`
        }
      });
      if (res.ok) {
        setTimeout(() => setLoadingMsg(''), 1000);
      } else {
        throw new Error('Failed to clear');
      }
    } catch (err) {
      alert('Error clearing disruptions');
      setLoadingMsg('');
    }
  };

  const handleRemoveDisruption = async (target) => {
    setLoadingMsg('Removing...');
    try {
      const res = await fetch(`${apiUrl}/api/v1/simulations/disruptions/${target}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${useStore.getState().token}`
        }
      });
      if (res.ok) {
        setTimeout(() => setLoadingMsg(''), 1000);
      } else {
        throw new Error('Failed to remove disruption');
      }
    } catch (err) {
      alert('Error removing disruption');
      setLoadingMsg('');
    }
  };

  const handleOptimize = async () => {
    setLoadingMsg('Optimizing route...');
    useStore.getState().resetSimulation();
    try {
      const res = await fetch(`${apiUrl}/api/v1/pathfinder/simulate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${useStore.getState().token}`
        },
        body: JSON.stringify({
          source_id: sourceNode,
          target_id: targetNode,
          avoid_edge_id: avoidEdgeId || undefined,
          optimization_mode: optimizationMode
        })
      });
      const data = await res.json();
      if (res.ok && data.nodes) {
        const mappedData = {
          path: data.nodes,
          lanes: data.lanes,
          total_distance_km: data.summary.total_distance_km,
          total_cost_usd: data.summary.total_cost_usd,
          mitigation_strategy: data.mitigation_strategy || null
        };
        useStore.getState().setActiveSimulationPath(mappedData);
      } else {
        alert('Simulation Refused: ' + (data.detail || "Error computing path."));
      }
    } catch (err) {
      alert('Error finding route');
    } finally {
      setLoadingMsg('');
    }
  };

  const renderMapControls = () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      {/* Simulation Controls */}
      <div className="glass-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ margin: 0, fontSize: 13, fontWeight: 700, letterSpacing: 0.5 }}>Scenario Control Room</h3>
          {role === 'admin' && <span style={{ fontSize: 9, background: 'var(--brand-purple)', padding: '2px 6px', borderRadius: 4, fontWeight: 800 }}>ADMIN</span>}
        </div>

        <div className="form-group">
          <label className="form-label">Disruption Type</label>
          <select className="select-input" value={disruptionType} onChange={e => setDisruptionType(e.target.value)}>
            <option value="hurricane">Cyclone / Hurricane</option>
            <option value="strike">Port Strike</option>
            <option value="blockade">Canal Blockade</option>
          </select>
        </div>

        <div className="form-group">
          <label className="form-label">Target Corridor / Port</label>
          <select className="select-input" value={targetEdge} onChange={e => setTargetEdge(e.target.value)}>
            <option value="CNSHA-USLAX">CNSHA ➔ USLAX (Trans-Pacific)</option>
            <option value="AEJEA-EGSUZ">AEJEA ➔ EGSUZ (Gulf-Red Sea)</option>
            <option value="CNSHA-KRPUS">CNSHA ➔ KRPUS (Intra-Asia)</option>
            <option value="EGSUZ-NLRTM">EGSUZ ➔ NLRTM (Suez-Europe)</option>
            <option value="SGSIN">SGSIN (Singapore Port)</option>
            <option value="SGSTR">SGSTR (Strait of Malacca)</option>
            <option value="LKCMB">LKCMB (Colombo Port)</option>
          </select>
        </div>

        <div className="form-group">
          <label className="form-label">Severity Level: {Math.round(severity * 100)}%</label>
          <input
            type="range" min="0" max="1" step="0.05"
            value={severity} onChange={e => setSeverity(parseFloat(e.target.value))}
            style={{ width: '100%', accentColor: severity > 0.7 ? 'var(--status-crit)' : 'var(--brand-blue)' }}
          />
        </div>

        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn-danger" style={{ flex: 1 }} onClick={handleInject} disabled={!!loadingMsg}>
            {loadingMsg || 'Inject Disruption'}
          </button>
          <button className="btn-secondary" style={{ flex: 1 }} onClick={handleClearDisruptions} disabled={!!loadingMsg}>
            Clear All
          </button>
        </div>

        {/* Active Disruptions List */}
        {disruptions && disruptions.length > 0 && (
          <div style={{ marginTop: '12px' }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', marginBottom: '8px', textTransform: 'uppercase' }}>Active Disruptions</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {disruptions.map(d => (
                <div key={d.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(239, 68, 68, 0.1)', borderLeft: '2px solid var(--status-crit)', padding: '6px 8px', borderRadius: '4px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column' }}>
                    <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--status-crit)' }}>{d.target}</span>
                    <span style={{ fontSize: 9, color: 'var(--text-secondary)' }}>
                      Severity: {Math.round(d.severity * 100)}%
                      {d.weather > 0 ? ` | Weather: ${d.weather}` : ''}
                    </span>
                  </div>
                  <button
                    onClick={() => handleRemoveDisruption(d.target)}
                    style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: '4px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                    title="Remove Disruption"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Pathfinding */}
      <div className="glass-card">
        <h3 style={{ margin: 0, fontSize: 13, fontWeight: 700, letterSpacing: 0.5 }}>AI Route Optimization</h3>

        <div style={{ display: 'flex', gap: 8 }}>
          <div className="form-group" style={{ flex: 1 }}>
            <label className="form-label">Origin</label>
            <select className="select-input" value={sourceNode} onChange={e => setSourceNode(e.target.value)}>
              {PORTS.map(p => <option key={p.id} value={p.id}>{p.name} ({p.id})</option>)}
            </select>
          </div>
          <div className="form-group" style={{ flex: 1 }}>
            <label className="form-label">Destination</label>
            <select className="select-input" value={targetNode} onChange={e => setTargetNode(e.target.value)}>
              {PORTS.map(p => <option key={p.id} value={p.id}>{p.name} ({p.id})</option>)}
            </select>
          </div>
        </div>

        <div className="form-group" style={{ marginTop: 8 }}>
          <label className="form-label">Avoid Corridor (Optional)</label>
          <select className="select-input" value={avoidEdgeId} onChange={e => setAvoidEdgeId(e.target.value)}>
            <option value="">None (Let AI decide)</option>
            {metrics && metrics.map(m => (
              <option key={m.id} value={m.id}>{m.name}</option>
            ))}
          </select>
        </div>

        <button className="btn-primary" onClick={handleOptimize} disabled={!!loadingMsg} style={{ marginTop: 8 }}>
          {loadingMsg || 'Calculate Optimal Route'}
        </button>

        {activeSimulationPath && (
          <div className="sub-card animate-fade-in" style={{ marginTop: 8, border: optimizationMode === 'essential' ? '1px solid rgba(251, 191, 36, 0.3)' : 'none' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="form-label" style={{ color: optimizationMode === 'essential' ? '#fbbf24' : 'var(--status-ok)' }}>
                {optimizationMode === 'essential' ? 'Humanitarian Route Established' : 'Route Established'}
              </span>
              <span style={{ fontSize: 12, fontWeight: 800 }}>{activeSimulationPath.total_distance_km} km</span>
            </div>
            
            {activeSimulationPath.total_cost_usd && (
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 4 }}>
                <span className="form-label" style={{ color: 'var(--text-muted)' }}>
                  {optimizationMode === 'essential' ? 'Expedited Air/Sea Freight Cost' : 'Estimated Freight Cost'}
                </span>
                <span style={{ fontSize: 12, fontWeight: 800, color: optimizationMode === 'essential' ? '#f87171' : 'var(--brand-blue)' }}>
                  ${activeSimulationPath.total_cost_usd.toLocaleString()}
                </span>
              </div>
            )}

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
              {activeSimulationPath.path.map((node, i) => (
                <React.Fragment key={i}>
                  <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-primary)' }}>{node}</span>
                  {i < activeSimulationPath.path.length - 1 && <span style={{ color: 'var(--text-muted)' }}>→</span>}
                </React.Fragment>
              ))}
            </div>

            {activeSimulationPath.mitigation_strategy && (
              <div style={{ 
                marginTop: 8, padding: 8, 
                background: optimizationMode === 'essential' ? 'rgba(251, 191, 36, 0.1)' : 'rgba(56, 189, 248, 0.1)', 
                borderLeft: `2px solid ${optimizationMode === 'essential' ? '#fbbf24' : 'var(--brand-blue)'}`, 
                borderRadius: 4 
              }}>
                <div style={{ 
                  fontSize: 9, fontWeight: 700, 
                  color: optimizationMode === 'essential' ? '#fbbf24' : 'var(--brand-blue)', 
                  marginBottom: 4, textTransform: 'uppercase',
                  display: 'flex', alignItems: 'center', gap: '4px'
                }}>
                  {optimizationMode === 'essential' ? '🚁 NGO Humanitarian Protocol' : 'AI Mitigation Strategy'}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                  {activeSimulationPath.mitigation_strategy}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div className="sidebar-viewport">
      {activeTab === 'map' && renderMapControls()}
      {activeTab === 'network' && <NetworkHealthGrid />}
      {activeTab === 'carbon' && <CarbonDashboard />}
      {activeTab === 'timeline' && <AlertsTimeline />}
      {activeTab === 'bookings' && <ActiveBookings />}
    </div>
  );
};

export default Sidebar;
