import React, { useState, useEffect } from 'react';

const apiUrl = import.meta.env.VITE_API_URL ?? '';

const TIER_COLORS = { eco: '#22c55e', standard: '#f59e0b', heavy: '#ef4444' };

const getLaneColor = (co2) => co2 < 120 ? TIER_COLORS.eco : co2 < 250 ? TIER_COLORS.standard : TIER_COLORS.heavy;

const EcoScoreRing = ({ score }) => {
  const color = score >= 70 ? '#22c55e' : score >= 40 ? '#f59e0b' : '#ef4444';
  const label = score >= 70 ? 'IMO Compliant' : score >= 40 ? 'Improving' : 'High Emitter';
  return (
    <div className="eco-score-ring" style={{ borderColor: color, boxShadow: `0 0 24px ${color}40` }}>
      <span style={{ fontSize: 26, fontWeight: 900, color, lineHeight: 1 }}>{score}</span>
      <span style={{ fontSize: 9, color: 'var(--text-muted)', fontWeight: 700, textAlign: 'center', marginTop: 2 }}>ECO SCORE</span>
      <span style={{ fontSize: 8, color, fontWeight: 700, marginTop: 1 }}>{label}</span>
    </div>
  );
};

const StatCard = ({ label, value, unit, color = 'var(--brand-blue)', icon }) => (
  <div style={{
    background: 'rgba(17,24,39,0.8)', border: '1px solid var(--border-subtle)',
    borderRadius: 8, padding: '12px 16px',
  }}>
    <div style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>
      {icon} {label}
    </div>
    <div style={{ fontSize: 22, fontWeight: 800, color, lineHeight: 1.1 }}>
      {value}<span style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-muted)', marginLeft: 4 }}>{unit}</span>
    </div>
  </div>
);

const CarbonDashboard = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = () => {
    setLoading(true);
    fetch(`${apiUrl}/api/v1/analytics/carbon`)
      .then((r) => r.json())
      .then((d) => { setData(d); setLoading(false); })
      .catch((e) => { setError(e.message); setLoading(false); });
  };

  useEffect(() => { fetchData(); }, []);

  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 400, flexDirection: 'column', gap: 12, color: 'var(--text-muted)' }}>
      <div style={{ fontSize: 32 }}>🌍</div>
      <div style={{ fontSize: 12 }}>Computing carbon footprint analytics...</div>
    </div>
  );

  if (error) return (
    <div style={{ padding: 24, color: '#ef4444', textAlign: 'center' }}>
      <div style={{ fontSize: 24, marginBottom: 8 }}>⚠️</div>
      Failed to load carbon analytics: {error}
      <div><button onClick={fetchData} style={{ marginTop: 12, padding: '8px 16px', cursor: 'pointer', background: 'var(--surface-3)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 6, fontSize: 12 }}>Retry</button></div>
    </div>
  );

  if (!data) return null;

  const ecoCount = data.eco_lanes_count;
  const total = data.total_lanes;
  const vsBaselinePos = data.emissions_vs_baseline_pct <= 0;

  return (
    <div style={{ padding: '0', display: 'flex', flexDirection: 'column', gap: 20 }} className="animate-fade-in">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <div>
          <h2 style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-primary)', margin: 0 }}>🌱 Carbon Footprint Analytics</h2>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>Fleet-wide CO₂ emissions · IMO 2030 compliance tracking · EU ETS cost exposure</div>
        </div>
        <button onClick={fetchData} style={{ padding: '6px 12px', fontSize: 11, cursor: 'pointer', background: 'rgba(34,197,94,0.1)', color: '#22c55e', border: '1px solid rgba(34,197,94,0.3)', borderRadius: 6, fontWeight: 700 }}>⟳ Refresh</button>
      </div>

      {/* ── Eco Score + Summary ────────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
        <EcoScoreRing score={data.eco_score} />
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {/* IMO 2030 progress */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>
              <span>IMO 2030 TARGET ALIGNMENT</span>
              <span>{data.eco_score}%</span>
            </div>
            <div className="progress-bar-track" style={{ height: 6 }}>
              <div className="progress-bar-fill" style={{
                width: `${data.eco_score}%`,
                background: `linear-gradient(90deg, #ef4444, #f59e0b, #22c55e)`,
              }} />
            </div>
          </div>
          {/* Eco lane count */}
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
            <span style={{ color: '#22c55e', fontWeight: 700 }}>{ecoCount}</span> of <span style={{ color: 'var(--brand-blue)', fontWeight: 700 }}>{total}</span> active lanes are below IMO eco-threshold (120 kg CO₂/TEU)
          </div>
          {/* VS baseline */}
          <div style={{ fontSize: 11, color: vsBaselinePos ? '#22c55e' : '#ef4444', fontWeight: 600 }}>
            {vsBaselinePos ? '✅' : '📈'} {Math.abs(data.emissions_vs_baseline_pct)}% {vsBaselinePos ? 'below' : 'above'} IPCC 2024 shipping baseline
          </div>
        </div>
      </div>

      {/* ── Key Metrics Grid ───────────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <StatCard label="Avg CO₂/Lane" value={Math.round(data.avg_co2_per_lane)} unit="kg/TEU" color="var(--brand-blue)" icon="📦" />
        <StatCard label="EU ETS Cost" value={data.ets_cost_eur_per_teu} unit="EUR/TEU" color="#f59e0b" icon="💶" />
        <StatCard label="Carbon Intensity" value={data.avg_co2_per_km_g} unit="g/TEU·km" color="#a855f7" icon="🛢️" />
        <StatCard label="IMO 2030 Target" value={Math.round(data.imo_2030_target_co2)} unit="kg/TEU" color="#22c55e" icon="🎯" />
      </div>

      {/* ── Scope 3 Breakdown ──────────────────────────────────────────────── */}
      <div style={{ background: 'rgba(17,24,39,0.8)', border: '1px solid var(--border-subtle)', borderRadius: 8, padding: '14px 16px' }}>
        <div className="section-label" style={{ marginBottom: 10 }}>SCOPE 3 CORRIDOR BREAKDOWN</div>
        {[
          { label: 'Short Haul (<3,000 km)', pct: data.scope3_breakdown.short_haul_pct, color: '#22c55e' },
          { label: 'Medium Haul (3,000–8,000 km)', pct: data.scope3_breakdown.medium_haul_pct, color: '#f59e0b' },
          { label: 'Long Haul (>8,000 km)', pct: data.scope3_breakdown.long_haul_pct, color: '#ef4444' },
        ].map(({ label, pct, color }) => (
          <div key={label} style={{ marginBottom: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-secondary)', marginBottom: 3 }}>
              <span>{label}</span><span style={{ color, fontWeight: 700 }}>{pct}%</span>
            </div>
            <div className="progress-bar-track" style={{ height: 5 }}>
              <div className="progress-bar-fill" style={{ width: `${pct}%`, background: color }} />
            </div>
          </div>
        ))}
      </div>

      {/* ── Worst Emitting Lanes ───────────────────────────────────────────── */}
      <div>
        <div className="section-label" style={{ marginBottom: 8 }}>🔴 TOP 5 HEAVIEST CARBON CORRIDORS</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {data.worst_lanes.map((lane, i) => (
            <div key={lane.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', background: 'var(--surface-2)', borderRadius: 6, border: `1px solid ${getLaneColor(lane.co2_per_teu)}30` }}>
              <span style={{ fontSize: 11, fontWeight: 800, color: 'var(--text-muted)', width: 16 }}>#{i + 1}</span>
              <span style={{ fontSize: 11, color: 'var(--text-secondary)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{lane.name}</span>
              <span style={{ fontSize: 12, fontWeight: 700, color: getLaneColor(lane.co2_per_teu), flexShrink: 0 }}>{lane.co2_per_teu} kg</span>
              <span style={{ fontSize: 10, color: 'var(--text-muted)', flexShrink: 0 }}>{lane.distance_km.toLocaleString()} km</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Best Eco Lanes ─────────────────────────────────────────────────── */}
      <div>
        <div className="section-label" style={{ marginBottom: 8 }}>🟢 TOP 5 ECO-OPTIMIZED CORRIDORS</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {data.best_lanes.map((lane, i) => (
            <div key={lane.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', background: 'var(--surface-2)', borderRadius: 6, border: '1px solid rgba(34,197,94,0.15)' }}>
              <span style={{ fontSize: 11, fontWeight: 800, color: '#22c55e', width: 16 }}>#{i + 1}</span>
              <span style={{ fontSize: 11, color: 'var(--text-secondary)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{lane.name}</span>
              <span style={{ fontSize: 12, fontWeight: 700, color: '#22c55e', flexShrink: 0 }}>{lane.co2_per_teu} kg</span>
              {lane.is_eco && <span style={{ fontSize: 9, fontWeight: 700, padding: '2px 6px', background: 'rgba(34,197,94,0.15)', color: '#22c55e', borderRadius: 3 }}>ECO</span>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default CarbonDashboard;
