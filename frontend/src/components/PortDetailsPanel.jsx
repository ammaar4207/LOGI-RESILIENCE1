import React, { useState, useEffect } from 'react';
import { useStore } from '../store';

const apiUrl = import.meta.env.VITE_API_URL ?? '';

const PortDetailsPanel = () => {
  const selectedPortId = useStore((s) => s.selectedPortId);
  const setSelectedPortId = useStore((s) => s.setSelectedPortId);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!selectedPortId) { setData(null); return; }
    setLoading(true);
    setError(null);
    fetch(`${apiUrl}/api/v1/analytics/ports/${selectedPortId}`)
      .then((r) => r.json())
      .then((d) => { setData(d); setLoading(false); })
      .catch((e) => { setError(e.message); setLoading(false); });
  }, [selectedPortId]);

  if (!selectedPortId) return null;

  const riskColor = (r) => r >= 0.7 ? '#ef4444' : r >= 0.45 ? '#f59e0b' : '#10b981';
  const statusLabel = (r) => r >= 0.7 ? 'CRITICAL' : r >= 0.45 ? 'WARNING' : 'STABLE';

  return (
    <div className="port-panel-overlay animate-fade-in">
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', letterSpacing: 1, fontWeight: 700 }}>PORT TERMINAL ANALYTICS</div>
          <div style={{ fontSize: 15, fontWeight: 800, color: 'var(--text-primary)', marginTop: 2 }}>{selectedPortId}</div>
        </div>
        <button
          onClick={() => setSelectedPortId(null)}
          style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 18, lineHeight: 1 }}
          aria-label="Close port panel"
        >✕</button>
      </div>

      {loading && (
        <div style={{ textAlign: 'center', padding: '20px 0', color: 'var(--text-muted)', fontSize: 12 }}>
          <div style={{ fontSize: 20, marginBottom: 8 }}>⚡</div>
          Querying port analytics...
        </div>
      )}
      {error && (
        <div style={{ padding: '12px', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 6, color: '#ef4444', fontSize: 11 }}>
          Failed to load port data: {error}
        </div>
      )}

      {data && !loading && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {/* Risk Indicator */}
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <div style={{
              width: 64, height: 64, borderRadius: '50%',
              border: `3px solid ${riskColor(data.avg_risk)}`,
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              boxShadow: `0 0 20px ${riskColor(data.avg_risk)}50`
            }}>
              <span style={{ fontSize: 18, fontWeight: 800, color: riskColor(data.avg_risk) }}>
                {Math.round(data.avg_risk * 100)}
              </span>
              <span style={{ fontSize: 8, color: 'var(--text-muted)', fontWeight: 600 }}>RISK</span>
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                <span className={`risk-badge ${statusLabel(data.avg_risk)}`}>{statusLabel(data.avg_risk)}</span>
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                Resilience Index: <span style={{ color: '#10b981', fontWeight: 700 }}>{data.resilience_index}/100</span>
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                Active lanes: <span style={{ color: 'var(--brand-blue)', fontWeight: 700 }}>{data.active_lanes}</span>
              </div>
            </div>
          </div>

          {/* Risk bar */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>
              <span>AVERAGE RISK</span><span>{(data.avg_risk * 100).toFixed(1)}%</span>
            </div>
            <div className="progress-bar-track">
              <div className="progress-bar-fill" style={{
                width: `${data.avg_risk * 100}%`,
                background: `linear-gradient(90deg, var(--status-ok), ${riskColor(data.avg_risk)})`
              }} />
            </div>
          </div>

          {/* Max risk */}
          <div style={{ fontSize: 10, color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between' }}>
            <span>Peak Risk:</span>
            <span style={{ color: riskColor(data.max_risk), fontWeight: 700 }}>{(data.max_risk * 100).toFixed(1)}%</span>
          </div>

          {/* Connected ports */}
          <div>
            <div className="section-label" style={{ marginBottom: 6 }}>Connected Corridors</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {data.connected_ports.map((pid) => (
                <span
                  key={pid}
                  onClick={() => setSelectedPortId(pid)}
                  style={{
                    fontSize: 10, fontWeight: 700, padding: '3px 7px',
                    background: 'rgba(56,189,248,0.08)', border: '1px solid rgba(56,189,248,0.2)',
                    borderRadius: 4, color: 'var(--brand-blue)', cursor: 'pointer', fontFamily: 'var(--font-mono)'
                  }}
                  title={`View ${pid} port details`}
                >{pid}</span>
              ))}
            </div>
          </div>

          {/* Active lanes */}
          <div>
            <div className="section-label" style={{ marginBottom: 6 }}>Active Trade Lanes</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 120, overflowY: 'auto' }}>
              {data.lane_details.slice(0, 5).map((lane) => (
                <div key={lane.id} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '6px 8px', background: 'var(--surface-2)', borderRadius: 4,
                  border: `1px solid ${lane.risk_score >= 0.7 ? 'rgba(239,68,68,0.3)' : 'var(--border-subtle)'}`
                }}>
                  <span style={{ fontSize: 10, color: 'var(--text-secondary)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {lane.name}
                  </span>
                  <span style={{ fontSize: 10, fontWeight: 700, marginLeft: 8, color: riskColor(lane.risk_score), flexShrink: 0 }}>
                    {Math.round(lane.risk_score * 100)}%
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Global context */}
          <div style={{ padding: '8px 10px', background: 'var(--surface-2)', borderRadius: 6, fontSize: 10, color: 'var(--text-muted)' }}>
            Global network: {data.global_context.total_lanes} active lanes · Resilience {data.global_context.global_resilience}/100
          </div>
        </div>
      )}
    </div>
  );
};

export default PortDetailsPanel;
