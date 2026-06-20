import React, { useState } from 'react';

const RouteSimulator = ({ metrics, optimizationMode, onSimulationResult, onClearSimulation }) => {
  const [sourceId, setSourceId] = useState('');
  const [targetId, setTargetId] = useState('');
  const [avoidEdgeId, setAvoidEdgeId] = useState('');
  const [simData, setSimData] = useState(null);
  const [loading, setLoading] = useState(false);

  // Extract unique ports map safely using exact IDs
  const portMap = new Map();
  metrics.forEach(m => {
    const parts = (m.name || '').split('➔').map(s => s.trim());
    if (m.source_id) {
      portMap.set(m.source_id.trim(), parts[0] || m.source_id);
    }
    if (m.target_id) {
      portMap.set(m.target_id.trim(), parts[1] || parts[0] || m.target_id);
    }
  });
  const uniquePorts = Array.from(portMap.entries()).map(([id, name]) => ({ id, name }));

  const triggerSimulation = async () => {
    if (!sourceId || !targetId) return;
    setLoading(true);
    try {
      // Build base configuration body explicitly
      const payload = {
        source_id: sourceId,
        target_id: targetId,
        optimization_mode: optimizationMode
      };

      // Strip empty values completely to avoid schema exception errors
      if (avoidEdgeId && avoidEdgeId.trim() !== "") {
        payload.avoid_edge_id = avoidEdgeId;
      }

      const apiUrl = import.meta.env.VITE_API_URL ?? '';
      const response = await fetch(`${apiUrl}/api/v1/pathfinder/simulate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      const data = await response.json();
      
      if (response.ok) {
        setSimData(data);
        onSimulationResult(data);
      } else {
        // Humanize potential structural array warnings cleanly without [object Object] artifacts
        const errorMessage = typeof data.detail === 'object' 
          ? JSON.stringify(data.detail, null, 2) 
          : (data.detail || "Error computing alternative path topology.");
        alert(`Simulation Refused:\n${errorMessage}`);
      }
    } catch (err) {
      console.error(err);
      alert(`Network connection fault: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const clearFields = () => {
    setSourceId('');
    setTargetId('');
    setAvoidEdgeId('');
    setSimData(null);
    onClearSimulation();
  };

  return (
    <div className="glass-card" style={{ marginTop: '20px' }}>
      <h3 style={{ fontSize: '13px', color: '#38bdf8', margin: '0 0 14px 0', textTransform: 'uppercase', fontWeight: 'bold', letterSpacing: '0.5px' }}>
        ⚡ Tactical Routing Simulator
      </h3>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <div className="form-group">
          <label className="form-label">Departure Origin</label>
          <select value={sourceId} onChange={(e) => setSourceId(e.target.value)} className="select-input">
            <option value="">Select Port...</option>
            {uniquePorts.map(p => <option key={`src-${p.id}`} value={p.id}>{p.name} ({p.id})</option>)}
          </select>
        </div>

        <div className="form-group">
          <label className="form-label">Destination Node</label>
          <select value={targetId} onChange={(e) => setTargetId(e.target.value)} className="select-input">
            <option value="">Select Port...</option>
            {uniquePorts.map(p => <option key={`dst-${p.id}`} value={p.id}>{p.name} ({p.id})</option>)}
          </select>
        </div>

        <div className="form-group">
          <label className="form-label">Simulate Lane Failure (Avoid Edge)</label>
          <select value={avoidEdgeId} onChange={(e) => setAvoidEdgeId(e.target.value)} className="select-input">
            <option value="">None (Keep All Lanes Open)</option>
            {metrics.map(m => <option key={`avoid-${m.id}`} value={m.id}>{m.name} [Risk: {m.risk_score}]</option>)}
          </select>
        </div>

        <div style={{ display: 'flex', gap: '8px', marginTop: '6px' }}>
          <button onClick={triggerSimulation} disabled={loading || !sourceId || !targetId} className="btn-primary" style={{ opacity: (loading || !sourceId || !targetId) ? 0.5 : 1 }}>
            {loading ? 'Calculating Path...' : 'Run Simulation'}
          </button>
          <button onClick={clearFields} className="btn-secondary">
            Reset
          </button>
        </div>
      </div>

      {simData && (
        <div className="sub-card" style={{ marginTop: '14px', borderColor: '#22d3ee50' }}>
          <div style={{ fontSize: '11px', fontWeight: 'bold', color: '#22d3ee', textTransform: 'uppercase', marginBottom: '8px' }}>
            Optimal Path Output Matrix
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '12px', color: '#94a3b8' }}>
            <div>Route Plan: <span style={{ color: '#fff', fontWeight: 'bold' }}>{simData.nodes.map(n => n.toUpperCase()).join(' ➔ ')}</span></div>
            <div>Cumulative Cost Weight: <span style={{ color: '#38bdf8' }}>{simData.summary.cost}</span></div>
            <div>Total Network Distance: <span style={{ color: '#f1f5f9' }}>{simData.summary.total_distance_km.toLocaleString()} km</span></div>
            <div>Emissions Footprint: <span style={{ color: '#10b981' }}>{simData.summary.total_co2_teu} kg CO₂/TEU</span></div>
            <div>Averaged Lane Risk: <span style={{ color: simData.summary.avg_risk_score > 0.5 ? '#f59e0b' : '#06b6d4' }}>{simData.summary.avg_risk_score}</span></div>
            <div>Route Resilience Index: <span style={{ color: '#22d3ee', fontWeight: 'bold' }}>{simData.summary.resilience_index ?? '—'}/100</span></div>
          </div>
        </div>
      )}
    </div>
  );
};

export default RouteSimulator;