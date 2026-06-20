import React from 'react';
import { useStore } from '../store';

const SecurityControl = () => {
  const token = useStore(state => state.token);
  const role = useStore(state => state.role);
  const securityLogs = useStore(state => state.securityLogs);
  const setToken = useStore(state => state.setToken);
  const setRole = useStore(state => state.setRole);
  const addSecurityLog = useStore(state => state.addSecurityLog);

  const roles = [
    { name: 'Administrator', value: 'admin', token: 'mock-admin-token', desc: 'Full write/delete scenario access' },
    { name: 'Dispatcher', value: 'dispatcher', token: 'mock-dispatcher-token', desc: 'Can inject disruptions, no admin configs' },
    { name: 'Viewer', value: 'viewer', token: 'mock-viewer-token', desc: 'Read-only metrics & simulation dashboard' },
    { name: 'Unauthorized', value: 'unauthorized', token: 'invalid-expired-token', desc: 'Simulate bad key / expired credentials' }
  ];

  const handleRoleChange = (selectedRole) => {
    setRole(selectedRole.value);
    setToken(selectedRole.token);
    addSecurityLog(`Switched authorization credentials to [${selectedRole.name}]`);
  };

  // Decode JWT payload for visualization
  const getMockJwtPayload = () => {
    const timeNow = Math.floor(Date.now() / 1000);
    return {
      alg: 'RS256',
      typ: 'JWT',
      kid: 'keycloak-sig-2026-logiresilience',
      payload: {
        exp: timeNow + 1800,
        iat: timeNow,
        iss: 'http://keycloak:8080/realms/logiresilience',
        aud: 'logi-resilience-api',
        sub: `usr_${role}_uuid`,
        preferred_username: `${role}_user`,
        email: `${role}@logiresilience.io`,
        realm_access: {
          roles: role === 'admin' ? ['admin', 'dispatcher', 'offline_access'] : role === 'dispatcher' ? ['dispatcher'] : role === 'viewer' ? ['viewer'] : []
        }
      }
    };
  };

  const mockJwt = getMockJwtPayload();

  return (
    <div className="glass-card" style={{ marginTop: '20px', borderLeft: '3px solid #6366f1' }}>
      <h3 style={{ fontSize: '13px', color: '#6366f1', margin: '0 0 14px 0', textTransform: 'uppercase', fontWeight: 'bold', letterSpacing: '0.5px', display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span className="pulsing-glow-dot" style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#6366f1', display: 'inline-block', boxShadow: '0 0 8px #6366f1' }} />
        🔐 Identity & Access Control Deck
      </h3>

      {/* Security Status */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 12px', backgroundColor: 'rgba(99, 102, 241, 0.08)', border: '1px solid rgba(99, 102, 241, 0.2)', borderRadius: '6px', marginBottom: '14px' }}>
        <div style={{ fontSize: '11px', color: '#94a3b8' }}>GATEWAY IAM PROVIDER:</div>
        <div style={{ fontSize: '12px', fontWeight: 'bold', color: '#a5b4fc', fontFamily: 'monospace' }}>
          {token.startsWith('mock') ? '⚙️ MOCK-OIDC BYPASS' : '🛡️ KEYCLOAK OIDC'}
        </div>
      </div>

      {/* Role Picker List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '16px' }}>
        <div style={{ fontSize: '11px', color: '#94a3b8', textTransform: 'uppercase', fontWeight: '600' }}>Active IAM Identities</div>
        {roles.map(r => (
          <div 
            key={r.value} 
            onClick={() => handleRoleChange(r)}
            style={{ 
              display: 'flex', 
              flexDirection: 'row', 
              alignItems: 'center', 
              padding: '10px 12px', 
              borderRadius: '6px', 
              border: `1px solid ${role === r.value ? 'rgba(99, 102, 241, 0.5)' : 'rgba(255, 255, 255, 0.05)'}`, 
              backgroundColor: role === r.value ? 'rgba(99, 102, 241, 0.12)' : 'rgba(15, 23, 42, 0.4)',
              cursor: 'pointer',
              transition: 'all 0.2s ease-in-out'
            }}
          >
            <div style={{ 
              width: '14px', 
              height: '14px', 
              borderRadius: '50%', 
              border: '2px solid #6366f1', 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center',
              marginRight: '12px',
              backgroundColor: role === r.value ? '#6366f1' : 'transparent'
            }}>
              {role === r.value && <div style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#fff' }} />}
            </div>
            <div style={{ flexGrow: 1 }}>
              <div style={{ fontSize: '12px', fontWeight: '600', color: role === r.value ? '#fff' : '#cbd5e1' }}>{r.name}</div>
              <div style={{ fontSize: '10px', color: '#64748b', marginTop: '1px' }}>{r.desc}</div>
            </div>
          </div>
        ))}
      </div>

      {/* JWT Inspector */}
      <div style={{ marginBottom: '16px' }}>
        <div style={{ fontSize: '11px', color: '#94a3b8', textTransform: 'uppercase', fontWeight: '600', marginBottom: '6px' }}>Active JWT Decoded Claim Set</div>
        <div style={{ 
          maxHeight: '120px', 
          overflowY: 'auto', 
          backgroundColor: '#090d16', 
          border: '1px solid #1e293b', 
          borderRadius: '6px', 
          padding: '8px 12px', 
          fontFamily: 'monospace', 
          fontSize: '10px', 
          color: '#38bdf8',
          lineHeight: '1.4'
        }}>
          <div><span style={{ color: '#f43f5e' }}>// Token Header</span></div>
          <div>{JSON.stringify({ alg: mockJwt.alg, typ: mockJwt.typ, kid: mockJwt.kid }, null, 2)}</div>
          <div style={{ height: '4px' }} />
          <div><span style={{ color: '#10b981' }}>// Token Payload</span></div>
          <div>{JSON.stringify(mockJwt.payload, null, 2)}</div>
        </div>
      </div>

      {/* Security Audit Console logs */}
      <div>
        <div style={{ fontSize: '11px', color: '#94a3b8', textTransform: 'uppercase', fontWeight: '600', marginBottom: '6px' }}>Identity Audit Console</div>
        <div style={{ 
          height: '90px', 
          overflowY: 'auto', 
          backgroundColor: '#030712', 
          border: '1px solid #111827', 
          borderRadius: '6px', 
          padding: '8px 12px', 
          fontFamily: 'monospace', 
          fontSize: '10px', 
          color: '#10b981',
          display: 'flex',
          flexDirection: 'column',
          gap: '4px'
        }}>
          {securityLogs.map((log, i) => (
            <div key={`log-${i}`} style={{ opacity: Math.max(0.3, 1 - i * 0.15) }}>{log}</div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default SecurityControl;
