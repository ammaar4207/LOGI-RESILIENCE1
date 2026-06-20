import React, { useEffect, useState } from 'react';
import { useStore } from '../store';

const ActiveBookings = () => {
  const camps = useStore(state => state.camps);
  const [bookings, setBookings] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchBookings = async () => {
      try {
        const apiUrl = import.meta.env.VITE_API_URL ?? '';
        const res = await fetch(`${apiUrl}/api/v1/simulations/bookings`, {
          headers: {
            'Authorization': `Bearer ${useStore.getState().token}`
          }
        });
        const data = await res.json();
        if (Array.isArray(data)) {
          setBookings(data);
        }
      } catch (err) {
        console.error("Failed to fetch active bookings:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchBookings();
    const interval = setInterval(fetchBookings, 5000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return <div style={{ padding: 24, color: 'var(--text-muted)' }}>Loading active bookings...</div>;
  }

  if (bookings.length === 0) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
        <h3 style={{ margin: '0 0 8px', color: 'var(--text-primary)' }}>No Active Bookings</h3>
        <p style={{ margin: 0 }}>There are currently no active automated re-bookings.</p>
      </div>
    );
  }

  return (
    <div style={{ padding: 24, height: '100%', overflowY: 'auto' }}>
      <h2 style={{ margin: '0 0 24px', color: '#10b981', display: 'flex', alignItems: 'center', gap: 8 }}>
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
        Active Carrier Bookings
      </h2>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))', gap: 16 }}>
        {bookings.map((b, idx) => {
          let campInfo = null;
          if (b.is_essential && camps && camps.length > 0 && b.alternative_lanes?.length > 0) {
            const lastLane = b.alternative_lanes[b.alternative_lanes.length - 1];
            const parts = lastLane.split('_');
            const destPort = parts.length === 3 ? parts[2] : null;
            if (destPort) {
              campInfo = camps.find(c => c.port_id === destPort);
            }
          }
          
          return (
          <div key={idx} style={{ background: 'var(--panel-bg)', border: '1px solid #334155', borderRadius: 8, padding: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
              <div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4 }}>Booking Ref</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: b.is_essential ? '#fbbf24' : '#10b981', letterSpacing: 1 }}>{b.booking_ref}</div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
                <div style={{ background: 'rgba(56, 189, 248, 0.1)', color: '#38bdf8', padding: '4px 8px', borderRadius: 4, fontSize: 10, fontWeight: 700 }}>
                  {b.lane_id}
                </div>
                {b.is_essential && (
                  <div style={{ background: 'rgba(251, 191, 36, 0.2)', color: '#fbbf24', padding: '4px 8px', borderRadius: 4, fontSize: 9, fontWeight: 800, textTransform: 'uppercase', letterSpacing: 1, border: '1px solid rgba(251, 191, 36, 0.4)' }}>
                    🚁 URGENT: Humanitarian Aid
                  </div>
                )}
              </div>
            </div>

            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4 }}>Detour Route</div>
              <div style={{ fontSize: 12, color: 'var(--text-primary)', lineHeight: 1.5 }}>
                {b.alternative_lanes.join(' ➔ ')}
              </div>
            </div>
            
            {campInfo && (
              <div style={{ marginBottom: 16, background: campInfo.current_days_supply <= 3 ? 'rgba(239, 68, 68, 0.1)' : 'rgba(16, 185, 129, 0.1)', border: `1px solid ${campInfo.current_days_supply <= 3 ? 'rgba(239, 68, 68, 0.3)' : 'rgba(16, 185, 129, 0.3)'}`, borderRadius: 6, padding: 12 }}>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6 }}>Destination: {campInfo.name}</div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 12, color: 'var(--text-primary)' }}>Days of Supply Remaining:</span>
                  <span style={{ fontSize: 16, fontWeight: 800, color: campInfo.current_days_supply <= 3 ? '#ef4444' : '#10b981' }}>{campInfo.current_days_supply} Days</span>
                </div>
              </div>
            )}

            <div>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4 }}>Shipper Notification</div>
              <div style={{ 
                background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, padding: 12, 
                fontSize: 11, color: '#cbd5e1', whiteSpace: 'pre-wrap', maxHeight: 150, overflowY: 'auto'
              }}>
                {b.email_content}
              </div>
            </div>
          </div>
        )})}
      </div>
    </div>
  );
};

export default ActiveBookings;
