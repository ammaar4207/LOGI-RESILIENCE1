import React, { useMemo } from 'react';
import { useStore } from '../store';

const NetworkHealthGrid = () => {
  const { metrics, meta, setSelectedPortId, setActiveTab, setMapViewState, addNotification } = useStore();

  const data = useMemo(() => {
    if (!metrics || metrics.length === 0) return null;

    const portMap = {};
    metrics.forEach(m => {
      for (const [pid_key, coords_key] of [["source_id", "source_coords"], ["target_id", "target_coords"]]) {
        const pid = m[pid_key]?.toUpperCase();
        if (!pid) continue;
        
        if (!portMap[pid]) {
          const parts = (m.name || '').split('➔');
          const pName = parts[pid_key === "source_id" ? 0 : 1]?.trim() || pid;
          portMap[pid] = {
            port_id: pid,
            name: pName,
            coords: m[coords_key] || [0, 0],
            risk_scores: [],
            lane_count: 0,
            congestion: m.congestion || 0,
          };
        }
        portMap[pid].risk_scores.push(m.risk_score || 0);
        portMap[pid].lane_count += 1;
        portMap[pid].congestion = Math.max(portMap[pid].congestion, m.congestion || 0);
      }
    });

    const ports_summary = Object.values(portMap).map(p => {
      const avg_risk = p.risk_scores.length > 0 
        ? p.risk_scores.reduce((a, b) => a + b, 0) / p.risk_scores.length 
        : 0.3;
      
      const status = avg_risk >= 0.70 ? "CRITICAL" : (avg_risk >= 0.45 ? "WARNING" : "STABLE");
      
      return {
        ...p,
        avg_risk: parseFloat(avg_risk.toFixed(3)),
        status,
        resilience_index: Math.round((1.0 - avg_risk) * 100),
      };
    });

    ports_summary.sort((a, b) => b.avg_risk - a.avg_risk);

    return {
      ports: ports_summary,
      global_resilience: meta.resilience !== null ? meta.resilience : 100,
    };
  }, [metrics, meta.resilience]);

  const handlePortClick = (port) => {
    setSelectedPortId(port.port_id);
    setMapViewState({
      longitude: port.coords[0],
      latitude: port.coords[1],
      zoom: 6,
      pitch: 45,
      bearing: 0,
      transitionDuration: 1500,
    });
    setActiveTab('map');
    addNotification({
      type: 'info',
      title: 'Navigating to Port',
      message: `Zooming to ${port.name} (${port.port_id}) terminal view.`,
    });
  };

  if (!data || !data.ports) {
    return <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted)' }}>Waiting for live telemetry...</div>;
  }

  return (
    <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div>
        <h2 style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-primary)', margin: 0 }}>🌐 Global Network Health</h2>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>Real-time terminal congestion and risk status across all connected nodes</div>
      </div>

      <div style={{ display: 'flex', gap: 16, background: 'rgba(17,24,39,0.8)', padding: 16, borderRadius: 8, border: '1px solid var(--border-subtle)' }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 700, marginBottom: 4 }}>GLOBAL RESILIENCE INDEX</div>
          <div style={{ fontSize: 28, fontWeight: 900, color: data.global_resilience >= 70 ? '#10b981' : data.global_resilience >= 45 ? '#f59e0b' : '#ef4444' }}>
            {data.global_resilience}/100
          </div>
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 700, marginBottom: 4 }}>ACTIVE TERMINALS</div>
          <div style={{ fontSize: 28, fontWeight: 900, color: 'var(--brand-blue)' }}>{data.ports.length}</div>
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 700, marginBottom: 4 }}>CRITICAL NODES</div>
          <div style={{ fontSize: 28, fontWeight: 900, color: '#ef4444' }}>
            {data.ports.filter(p => p.status === 'CRITICAL').length}
          </div>
        </div>
      </div>

      <div className="network-grid">
        {data.ports.map((port) => (
          <div key={port.port_id} className={`network-port-card ${port.status}`} onClick={() => handlePortClick(port)}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
              <div>
                <div style={{ fontSize: 14, fontWeight: 800, color: 'var(--text-primary)' }}>{port.port_id}</div>
                <div style={{ fontSize: 10, color: 'var(--text-secondary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 120 }}>{port.name}</div>
              </div>
              <span className={`risk-badge ${port.status}`}>{port.status}</span>
            </div>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-muted)' }}>
                <span>Resilience:</span>
                <span style={{ fontWeight: 700, color: port.resilience_index >= 70 ? '#10b981' : port.resilience_index >= 45 ? '#f59e0b' : '#ef4444' }}>{port.resilience_index}/100</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-muted)' }}>
                <span>Active Lanes:</span>
                <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{port.lane_count}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default NetworkHealthGrid;
