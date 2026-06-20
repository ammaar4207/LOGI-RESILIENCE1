import React, { useEffect, useState } from 'react';
import { useStore } from '../store';

const TOAST_ICONS = {
  success: '✅',
  warning: '⚠️',
  error: '🚨',
  info: 'ℹ️',
  ngo: '🚁', // Helicopter/Humanitarian aid icon
};

const TOAST_DURATION = 6000;

const Toast = ({ notification, onDismiss }) => {
  const [exiting, setExiting] = useState(false);

  const dismiss = () => {
    setExiting(true);
    setTimeout(() => onDismiss(notification.id), 250);
  };

  useEffect(() => {
    const timer = setTimeout(dismiss, TOAST_DURATION);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div className={`toast ${notification.type || 'info'} ${exiting ? 'exiting' : ''}`}>
      <span className="toast-icon">{TOAST_ICONS[notification.type] || 'ℹ️'}</span>
      <div className="toast-body">
        <div className="toast-title">{notification.title}</div>
        {notification.message && (
          <div className="toast-message">{notification.message}</div>
        )}
      </div>
      <button className="toast-close" onClick={dismiss}>✕</button>
    </div>
  );
};

const NotificationToast = () => {
  const notifications = useStore((s) => s.notifications);
  const dismissNotification = useStore((s) => s.dismissNotification);
  const metrics = useStore((s) => s.metrics);
  const meta = useStore((s) => s.meta);
  const addNotification = useStore((s) => s.addNotification);
  const lastAlertRef = React.useRef({ resilience: null, criticals: new Set() });

  // Auto-generate alerts when resilience drops or routes go critical
  useEffect(() => {
    const resilience = meta.resilience;
    const last = lastAlertRef.current;

    if (resilience !== null && resilience < 50 && last.resilience >= 50) {
      addNotification({
        type: 'error',
        title: '🚨 Global Resilience Critical',
        message: `Network resilience dropped to ${resilience}/100. Emergency rerouting recommended.`,
      });
    }
    last.resilience = resilience;

    const currentCriticals = new Set(
      metrics.filter((m) => m.status === 'CRITICAL').map((m) => m.id)
    );
    currentCriticals.forEach((id) => {
      if (!last.criticals.has(id)) {
        const lane = metrics.find((m) => m.id === id);
        addNotification({
          type: 'error',
          title: '⚠️ Critical Route Failure',
          message: `${lane?.name || id} has exceeded critical risk threshold (${Math.round((lane?.risk_score || 0) * 100)}%).`,
        });
      }
    });
    last.criticals = currentCriticals;
  }, [metrics, meta.resilience]);

  if (notifications.length === 0) return null;

  return (
    <div className="toast-container">
      {notifications.slice(0, 5).map((n) => (
        <Toast key={n.id} notification={n} onDismiss={dismissNotification} />
      ))}
    </div>
  );
};

export default NotificationToast;
