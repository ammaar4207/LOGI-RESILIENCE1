import { useState, useEffect, useRef, useCallback } from 'react';
import { useStore } from '../store';

const BACKOFF_INTERVALS = [1000, 2000, 4000, 8000, 15000, 30000];

export const useRiskStream = () => {
  const [payload, setPayload] = useState(null);
  const setWsStatus = useStore((s) => s.setWsStatus);
  const addNotification = useStore((s) => s.addNotification);
  const socketRef = useRef(null);
  const attemptRef = useRef(0);
  const unmountedRef = useRef(false);
  const reconnectTimerRef = useRef(null);

  const connect = useCallback(() => {
    if (unmountedRef.current) return;

    const base = import.meta.env.VITE_API_URL ?? '';
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = base
      ? base.replace(/^http/, 'ws') + '/api/v1/stream'
      : `${protocol}//${window.location.host}/api/v1/stream`;

    const attempt = attemptRef.current;
    if (attempt === 0) {
      setWsStatus('CONNECTING');
    } else {
      setWsStatus('RECONNECTING');
      addNotification({
        type: 'warning',
        title: 'Stream Reconnecting',
        message: `Attempting reconnect #${attempt} to live data stream...`,
      });
    }

    const socket = new WebSocket(wsUrl);
    socketRef.current = socket;

    socket.onopen = () => {
      if (unmountedRef.current) { socket.close(); return; }
      attemptRef.current = 0;
      setWsStatus('OPEN');
      if (attempt > 0) {
        addNotification({
          type: 'success',
          title: 'Stream Restored',
          message: 'Live telemetry connection re-established.',
        });
      }
    };

    socket.onmessage = (event) => {
      if (unmountedRef.current) return;
      try {
        const parsed = JSON.parse(event.data);
        if (parsed?.type === 'heartbeat' || parsed?.type === 'pong') return;

        if (parsed?.agent_proposal) {
          useStore.getState().setAgentProposal(parsed.agent_proposal);
          const optMode = useStore.getState().optimizationMode;
          const msg = optMode === 'essential' && parsed.agent_proposal.summary_essential 
             ? parsed.agent_proposal.summary_essential 
             : parsed.agent_proposal.summary;

          addNotification({
            type: optMode === 'essential' ? 'ngo' : 'info',
            title: optMode === 'essential' ? 'NGO Mitigation Proposal' : 'Agent Mitigation Proposal',
            message: msg,
          });
        } else if (Array.isArray(parsed) && parsed.length > 0 && parsed[0].mmsi) {
          // AIS Telemetry Payload
          useStore.getState().setAisShips(parsed);
        } else if (['iot_alert', 'gdacs_alert', 'ngo_alert', 'dcsa_event', 'notification'].includes(parsed?.type)) {
          // Suppress live background telemetry popups if the user is looking at a future forecast
          if (useStore.getState().forecastDays > 0) return;

          // GDACS / IoT / DCSA / NGO Alerts
          let alertType = 'warning';
          if (parsed.level === 'CRITICAL') alertType = 'error';
          if (parsed.level === 'INFO') alertType = 'info';
          if (parsed.type === 'ngo_alert') alertType = 'ngo'; // Special humanitarian styling

          addNotification({
            type: alertType,
            title: parsed.type === 'ngo_alert' ? '⚠️ NGO EARLY WARNING' : (parsed.source || parsed.title || 'System Alert'),
            message: parsed.message,
          });
        } else if (parsed && (parsed.status === 'OPERATIONAL' || parsed.status === 'DEGRADED')) {
          setPayload(parsed);
        }
      } catch {
        // ignore malformed frames
      }
    };

    socket.onerror = () => {
      if (unmountedRef.current) return;
      setWsStatus('RECONNECTING');
    };

    socket.onclose = (event) => {
      if (unmountedRef.current) return;
      if (event.wasClean) {
        setWsStatus('FAILED');
        return;
      }
      // Exponential backoff reconnect
      const delay = BACKOFF_INTERVALS[Math.min(attemptRef.current, BACKOFF_INTERVALS.length - 1)];
      attemptRef.current += 1;
      reconnectTimerRef.current = setTimeout(connect, delay);
    };
  }, [setWsStatus, addNotification]);

  useEffect(() => {
    unmountedRef.current = false;
    connect();
    return () => {
      unmountedRef.current = true;
      clearTimeout(reconnectTimerRef.current);
      if (socketRef.current) {
        socketRef.current.close(1000, 'Component unmounted');
      }
    };
  }, [connect]);

  return payload;
};