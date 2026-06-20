import React from 'react';

const RiskPanel = ({ metrics, history, optimizationMode }) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', color: '#f8fafc' }}>
      
      {/* Transit Appraisal List */}
      <div>
        <h2 style={{ fontSize: '13px', color: '#94a3b8', margin: '0 0 12px 0', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
          Trade Corridor Matrix Analysis
        </h2>
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {metrics.map((lane) => {
            const badgeColor = lane.status === 'CRITICAL' ? '#ef4444' : lane.status === 'WARNING' ? '#f59e0b' : '#06b6d4';
            const xai = lane.xai_attribution;
            const carbon = lane.carbon_metrics || { distance_km: 5000, co2_per_teu: 150 };

            return (
              <div key={lane.id} className="glass-card">
                
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h3 style={{ fontSize: '13px', fontWeight: 'bold', margin: 0, color: '#f1f5f9' }}>{lane.name}</h3>
                  <span style={{ fontSize: '11px', fontWeight: 'bold', color: badgeColor, padding: '2px 8px', borderRadius: '4px', backgroundColor: `${badgeColor}15`, border: `1px solid ${badgeColor}30` }}>
                    {lane.status} · R:{lane.risk_score} · Res:{lane.resilience_index ?? Math.round((1 - lane.risk_score) * 100)}
                  </span>
                </div>

                {optimizationMode === 'resilience' ? (
                  <div className="sub-card">
                    <div style={{ fontSize: '11px', fontWeight: 'bold', color: '#38bdf8', textTransform: 'uppercase' }}>Physics-Informed XAI Attribution (SHAP)</div>
                    
                    {[
                      { label: 'Environmental Stress (Weather)', val: xai?.environmental || 33, color: '#06b6d4' },
                      { label: 'Operational Friction (Congestion)', val: xai?.operational || 33, color: '#a855f7' },
                      { label: 'Geopolitical Stability (RSS)', val: xai?.geopolitical || 34, color: '#f59e0b' }
                    ].map(vector => (
                      <div key={vector.label} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#94a3b8' }}>
                          <span>{vector.label}</span>
                          <span style={{ color: '#f1f5f9' }}>{vector.val}%</span>
                        </div>
                        <div style={{ width: '100%', height: '4px', backgroundColor: '#1e293b', borderRadius: '2px' }}>
                          <div style={{ width: `${vector.val}%`, height: '100%', backgroundColor: vector.color, transition: 'width 0.8s cubic-bezier(0.4, 0, 0.2, 1)' }} />
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="sub-card" style={{ borderLeft: '3px solid #10b981' }}>
                    <div style={{ fontSize: '11px', fontWeight: 'bold', color: '#10b981', textTransform: 'uppercase' }}>Carbon Footprint Telemetry</div>
                    
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                      <span style={{ color: '#94a3b8' }}>Total Transit Distance:</span>
                      <span style={{ color: '#f1f5f9', fontWeight: '600' }}>{carbon.distance_km.toLocaleString()} km</span>
                    </div>
                    
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                      <span style={{ color: '#94a3b8' }}>Carbon Intensity:</span>
                      <span style={{ color: carbon.co2_per_teu > 300 ? '#f43f5e' : '#10b981', fontWeight: 'bold' }}>
                        {carbon.co2_per_teu} kg CO₂ / TEU
                      </span>
                    </div>

                    {lane.status !== 'STABLE' && carbon.co2_per_teu < 200 && (
                      <div style={{ fontSize: '11px', color: '#f59e0b', backgroundColor: '#f59e0b10', padding: '6px', borderRadius: '4px', marginTop: '4px', border: '1px solid #f59e0b20' }}>
                        ⚠️ Tradeoff: Low footprint path, but faces active operational disruptions.
                      </div>
                    )}
                  </div>
                )}

              </div>
            );
          })}
        </div>
      </div>

    </div>
  );
};

export default RiskPanel;