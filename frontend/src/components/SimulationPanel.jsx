import React, { useState, useEffect } from 'react';

import { useStore } from '../store';

const SimulationPanel = ({ metrics }) => {
  const disruptions = useStore(state => state.disruptions);
  const setDisruptions = useStore(state => state.setDisruptions);
  const token = useStore(state => state.token);
  const addSecurityLog = useStore(state => state.addSecurityLog);
  const [type, setType] = useState('strike');
  const [targetPort, setTargetPort] = useState('');
  const [targetRoute, setTargetRoute] = useState('');
  const [severity, setSeverity] = useState(0.85);
  const [radiusKm, setRadiusKm] = useState(1000);
  const [loading, setLoading] = useState(false);

  const apiUrl = import.meta.env.VITE_API_URL ?? '';

  // Extract unique ports from metrics
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

  // Load active disruptions from backend
  const loadDisruptions = async () => {
    try {
      const response = await fetch(`${apiUrl}/api/v1/simulations/disruptions`);
      if (response.ok) {
        const data = await response.json();
        setDisruptions(data);
      }
    } catch (err) {
      console.error("Failed to load disruptions:", err);
    }
  };

  useEffect(() => {
    loadDisruptions();
  }, [metrics]);

  const injectDisruption = async () => {
    let target = '';
    let label = '';
    let lat = null;
    let lon = null;

    if (type === 'strike') {
      if (!targetPort) return;
      target = targetPort;
      const portName = portMap.get(targetPort) || targetPort;
      label = `Port Strike: ${portName}`;
      // Get lat/lon
      const routeWithPort = metrics.find(m => m.source_id === targetPort || m.target_id === targetPort);
      if (routeWithPort) {
        if (routeWithPort.source_id === targetPort) {
          lat = routeWithPort.source_coords[1];
          lon = routeWithPort.source_coords[0];
        } else {
          lat = routeWithPort.target_coords[1];
          lon = routeWithPort.target_coords[0];
        }
      }
    } else if (type === 'blockade') {
      if (!targetRoute) return;
      target = targetRoute;
      const route = metrics.find(m => m.id === targetRoute);
      label = `Corridor Blockade: ${route ? route.name : targetRoute}`;
      if (route) {
        // midpoint of route
        lat = (route.source_coords[1] + route.target_coords[1]) / 2;
        lon = (route.source_coords[0] + route.target_coords[0]) / 2;
      }
    } else if (type === 'hurricane') {
      if (!targetPort) return;
      target = targetPort;
      const portName = portMap.get(targetPort) || targetPort;
      label = `Typhoon near ${portName}`;
      // Get lat/lon of targeted port
      const routeWithPort = metrics.find(m => m.source_id === targetPort || m.target_id === targetPort);
      if (routeWithPort) {
        if (routeWithPort.source_id === targetPort) {
          lat = routeWithPort.source_coords[1];
          lon = routeWithPort.source_coords[0];
        } else {
          lat = routeWithPort.target_coords[1];
          lon = routeWithPort.target_coords[0];
        }
      }
    }

    const newDisruption = {
      id: `dis_${Date.now()}`,
      type,
      target,
      severity: parseFloat(severity),
      weather: type === 'hurricane' ? parseFloat(severity) : 0.1,
      congestion: type === 'strike' ? parseFloat(severity) : 0.1,
      news: parseFloat(severity),
      radius_km: type === 'hurricane' ? parseFloat(radiusKm) : 0,
      lat,
      lon,
      label
    };

    const updatedList = [...disruptions, newDisruption];
    setLoading(true);

    try {
      addSecurityLog(`POST /api/v1/simulations/disruptions - Initiating (token: ${token.slice(0, 15)}...)`);
      const response = await fetch(`${apiUrl}/api/v1/simulations/disruptions`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(updatedList)
      });
      if (response.ok) {
        addSecurityLog("POST /api/v1/simulations/disruptions - Authorized (200 OK)");
        setDisruptions(updatedList);
        // Reset selections
        setTargetPort('');
        setTargetRoute('');
      } else {
        addSecurityLog(`POST /api/v1/simulations/disruptions - Denied (${response.status} ${response.statusText})`);
        alert(`Failed to inject simulation disruption. Status: ${response.status} ${response.statusText}`);
      }
    } catch (err) {
      addSecurityLog(`POST /api/v1/simulations/disruptions - Network Error: ${err.message}`);
      alert(`Network error injecting disruption: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const removeDisruption = async (id) => {
    const updatedList = disruptions.filter(d => d.id !== id);
    setLoading(true);
    try {
      if (updatedList.length === 0) {
        await clearAllDisruptions();
      } else {
        addSecurityLog(`POST /api/v1/simulations/disruptions (remove) - Initiating`);
        const response = await fetch(`${apiUrl}/api/v1/simulations/disruptions`, {
          method: 'POST',
          headers: { 
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify(updatedList)
        });
        if (response.ok) {
          addSecurityLog("POST /api/v1/simulations/disruptions (remove) - Authorized (200 OK)");
          setDisruptions(updatedList);
        } else {
          addSecurityLog(`POST /api/v1/simulations/disruptions (remove) - Denied (${response.status})`);
          alert(`Failed to update disruptions: ${response.statusText}`);
        }
      }
    } catch (err) {
      alert(`Failed to remove disruption: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const clearAllDisruptions = async () => {
    setLoading(true);
    try {
      addSecurityLog(`DELETE /api/v1/simulations/disruptions - Initiating`);
      const response = await fetch(`${apiUrl}/api/v1/simulations/disruptions`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (response.ok) {
        addSecurityLog("DELETE /api/v1/simulations/disruptions - Authorized (200 OK)");
        setDisruptions([]);
      } else {
        addSecurityLog(`DELETE /api/v1/simulations/disruptions - Denied (${response.status})`);
        alert(`Failed to clear disruptions. Status: ${response.status}`);
      }
    } catch (err) {
      addSecurityLog(`DELETE /api/v1/simulations/disruptions - Network Error: ${err.message}`);
      alert(`Failed to clear disruptions: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass-card" style={{ marginTop: '20px' }}>
      <h3 style={{ fontSize: '13px', color: '#f43f5e', margin: '0 0 14px 0', textTransform: 'uppercase', fontWeight: 'bold', letterSpacing: '0.5px' }}>
        🛠️ Scenario Simulator Control Room
      </h3>

      {/* Active Disruptions List */}
      {disruptions.length > 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '14px' }}>
          <div style={{ fontSize: '11px', color: '#94a3b8', textTransform: 'uppercase', fontWeight: '600' }}>Active Disruption Overlays</div>
          {disruptions.map(d => (
            <div key={d.id} className="sub-card" style={{ borderColor: '#f43f5e50', padding: '8px 12px', display: 'flex', flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ fontSize: '12px' }}>
                <span style={{ color: '#f43f5e', fontWeight: 'bold', marginRight: '6px' }}>
                  {d.type === 'strike' ? '🔴 Strike' : d.type === 'hurricane' ? '🌀 Storm' : '⚠️ Blockage'}
                </span>
                <span style={{ color: '#f1f5f9' }}>{d.label}</span>
                <div style={{ fontSize: '10px', color: '#64748b', marginTop: '2px' }}>
                  Severity: {d.severity} {d.radius_km > 0 && `· Radius: ${d.radius_km} km`}
                </div>
              </div>
              <button 
                onClick={() => removeDisruption(d.id)} 
                style={{ background: 'transparent', border: 'none', color: '#64748b', cursor: 'pointer', fontSize: '14px', padding: '4px' }}
                onMouseOver={(e) => e.target.style.color = '#f43f5e'}
                onMouseOut={(e) => e.target.style.color = '#64748b'}
              >
                ✕
              </button>
            </div>
          ))}
          <button onClick={clearAllDisruptions} disabled={loading} className="btn-secondary" style={{ backgroundColor: '#ef444420', color: '#ef4444', border: '1px solid #ef444440', width: '100%', marginTop: '4px' }}>
            Reset System (Clear All Disruptions)
          </button>
        </div>
      ) : (
        <div style={{ fontSize: '12px', color: '#64748b', textAlign: 'center', padding: '10px 0', border: '1px dashed rgba(255,255,255,0.05)', borderRadius: '6px', marginBottom: '14px' }}>
          No active disruptions. System in nominal state.
        </div>
      )}

      {/* Disruption Injector Form */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '14px' }}>
        <div className="form-group">
          <label className="form-label">Disruption Scenario Type</label>
          <select value={type} onChange={(e) => setType(e.target.value)} className="select-input">
            <option value="strike">Port Industrial Action (Strike)</option>
            <option value="hurricane">Extreme Weather Event (Hurricane)</option>
            <option value="blockade">Trade Lane Blockage (Canal/Strait)</option>
          </select>
        </div>

        {type === 'strike' && (
          <div className="form-group">
            <label className="form-label">Target Port Terminal</label>
            <select value={targetPort} onChange={(e) => setTargetPort(e.target.value)} className="select-input">
              <option value="">Select Port...</option>
              {uniquePorts.map(p => <option key={`sim-port-${p.id}`} value={p.id}>{p.name} ({p.id})</option>)}
            </select>
          </div>
        )}

        {type === 'hurricane' && (
          <>
            <div className="form-group">
              <label className="form-label">Storm Center Port</label>
              <select value={targetPort} onChange={(e) => setTargetPort(e.target.value)} className="select-input">
                <option value="">Select Center...</option>
                {uniquePorts.map(p => <option key={`sim-storm-${p.id}`} value={p.id}>{p.name} ({p.id})</option>)}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Storm Impact Radius: {radiusKm} km</label>
              <input 
                type="range" 
                min="300" 
                max="2500" 
                step="100" 
                value={radiusKm} 
                onChange={(e) => setRadiusKm(e.target.value)}
                style={{ width: '100%', accentColor: '#f43f5e' }}
              />
            </div>
          </>
        )}

        {type === 'blockade' && (
          <div className="form-group">
            <label className="form-label">Target Trade Lane</label>
            <select value={targetRoute} onChange={(e) => setTargetRoute(e.target.value)} className="select-input">
              <option value="">Select Corridor...</option>
              {metrics.map(m => <option key={`sim-route-${m.id}`} value={m.id}>{m.name}</option>)}
            </select>
          </div>
        )}

        <div className="form-group">
          <label className="form-label">Disruption Severity: {Math.round(severity * 100)}%</label>
          <input 
            type="range" 
            min="0.3" 
            max="1.0" 
            step="0.05" 
            value={severity} 
            onChange={(e) => setSeverity(e.target.value)}
            style={{ width: '100%', accentColor: '#f43f5e' }}
          />
        </div>

        <button 
          onClick={injectDisruption} 
          disabled={loading || (type !== 'blockade' && !targetPort) || (type === 'blockade' && !targetRoute)} 
          className="btn-primary" 
          style={{ backgroundColor: '#f43f5e', color: '#ffffff', opacity: (loading || (type !== 'blockade' && !targetPort) || (type === 'blockade' && !targetRoute)) ? 0.5 : 1 }}
        >
          {loading ? 'Injecting Disruption...' : 'Inject Disruption Signal'}
        </button>
      </div>
    </div>
  );
};

export default SimulationPanel;
