import { useEffect } from 'react';


export default function Toast({ message, onClose, timeout = 8000 }) {
  useEffect(() => {
    if (!message) return;
    const timer = setTimeout(onClose, timeout);
    return () => clearTimeout(timer);
  }, [message, onClose, timeout]);


  useEffect(() => {
    if (!message) return;
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [message, onClose]);

  if (!message) return null;

  return (
    <div className="toast" role="alert" aria-live="assertive">
      <svg className="toast-icon" viewBox="0 0 24 24" fill="none"
           stroke="currentColor" strokeWidth="1.9" strokeLinecap="round">
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7.5v5M12 16.2v.3" />
      </svg>

      <div className="toast-body">
        <strong>Request failed</strong>
        <p>{message}</p>
      </div>

      <button className="toast-close" onClick={onClose} aria-label="Dismiss">
        ×
      </button>
    </div>
  );
}
