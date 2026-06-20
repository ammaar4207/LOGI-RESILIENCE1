import React, { useState, useEffect } from 'react';

const apiUrl = import.meta.env.VITE_API_URL ?? '';

const AlertsTimeline = () => {
  const [data, setData] = useState({ events: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = () => {
    fetch(`${apiUrl}/api/v1/analytics/events?limit=50`)
      .then((r) => r.json())
      .then((d) => { setData(d); setLoading(false); })
      .catch((e) => { setError(e.message); setLoading(false); });
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  const getEventColor = (type, severity) => {
    if (type === 'disruption_injected') return '#ef4444';
    if (type === 'disruption_cleared') return '#22c55e';
    if (type === 'alert_fired') return '#f59e0b';
    if (type === 'route_simulated') return '#38bdf8';
    if (severity >= 0.7) return '#ef4444';
    if (severity >= 0.4) return '#f59e0b';
    return '#64748b';
  };

  const getEventIcon = (type) => {
    if (type === 'disruption_injected') return '⚡';
    if (type === 'disruption_cleared') return '✅';
    if (type === 'alert_fired') return '⚠️';
    if (type === 'route_simulated') return '🗺️';
    return '🔹';
  };

  const formatTime = (isoString) => {
    const d = new Date(isoString);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  if (loading && data.events.length === 0) return <div style={{ padding: 20, color: 'var(--text-muted)' }}>Loading timeline...</div>;
  if (error) return <div style={{ padding: 20, color: '#ef4444' }}>Error: {error}</div>;

  return (
    <div className="animate-fade-in" style={{ padding: '0', display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, flexShrink: 0 }}>
        <div>
          <h2 style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-primary)', margin: 0 }}>📜 System Event Timeline</h2>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>Immutable audit log of all system actions and network state changes</div>
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-secondary)', background: 'var(--surface-3)', padding: '4px 10px', borderRadius: 12 }}>
          {data.total} Events Logged
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', paddingRight: 10, position: 'relative' }}>
        {data.events.length === 0 ? (
          <div style={{ textAlign: 'center', color: 'var(--text-muted)', marginTop: 40 }}>No events recorded yet.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
            {data.events.map((evt, idx) => {
              const isLast = idx === data.events.length - 1;
              const color = getEventColor(evt.event_type, evt.severity);
              return (
                <div key={evt.id} className="timeline-item" style={{ paddingBottom: isLast ? 0 : 20 }}>
                  {!isLast && <div className="timeline-line" />}
                  <div className="timeline-dot" style={{ background: color, boxShadow: `0 0 10px ${color}50` }} />
                  
                  <div style={{ flex: 1, background: 'rgba(17,24,39,0.6)', border: '1px solid var(--border-subtle)', borderRadius: 8, padding: '10px 14px', marginTop: '-4px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span>{getEventIcon(evt.event_type)}</span>
                        <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)', textTransform: 'capitalize' }}>
                          {evt.event_type.replace('_', ' ')}
                        </span>
                      </div>
                      <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{formatTime(evt.created_at)}</span>
                    </div>

                    <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                      {evt.target && <span>Target: <strong style={{ color: 'var(--text-primary)' }}>{evt.target}</strong></span>}
                      {evt.severity !== null && <span style={{ marginLeft: 10 }}>Severity: <strong style={{ color: color }}>{(evt.severity * 100).toFixed(0)}%</strong></span>}
                    </div>

                    {evt.details && (
                      <div style={{ marginTop: 8, padding: '8px', background: 'var(--surface-2)', borderRadius: 4, fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', overflowX: 'auto' }}>
                        {typeof evt.details === 'string' ? evt.details : JSON.stringify(evt.details)}
                      </div>
                    )}

                    <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 10, fontSize: 10, color: 'var(--text-muted)' }}>
                      <span>Actor: {evt.actor}</span>
                      {evt.global_resilience && <span>Resilience at event: <strong style={{ color: '#10b981' }}>{evt.global_resilience.toFixed(0)}/100</strong></span>}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default AlertsTimeline;
