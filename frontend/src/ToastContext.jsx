import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { IconAlert, IconCheck, IconInfo, IconX } from "./components/icons";

// Lightweight toast system. Toasts are the app's "you can still take that back" surface:
// every reversible action (approve, reject, restore, member changes) confirms here with
// an Undo, instead of a blocking "are you sure?" dialog.
const ToastContext = createContext(null);

let nextId = 1;
const MAX = 3;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const dismiss = useCallback((id) => {
    setToasts((ts) => ts.map((t) => (t.id === id ? { ...t, leaving: true } : t)));
    setTimeout(() => setToasts((ts) => ts.filter((t) => t.id !== id)), 220);
  }, []);

  const toast = useCallback((opts) => {
    const id = nextId++;
    const t = { id, tone: "default", duration: 5000, ...(typeof opts === "string" ? { title: opts } : opts) };
    setToasts((ts) => [...ts.slice(-(MAX - 1)), t]);
    return id;
  }, []);

  const api = useMemo(() => ({ toast, dismiss }), [toast, dismiss]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <section className="toast-region" aria-label="Notifications">
        {toasts.map((t) => (
          <Toast key={t.id} t={t} onDismiss={() => dismiss(t.id)} />
        ))}
      </section>
    </ToastContext.Provider>
  );
}

const ICONS = { success: IconCheck, error: IconAlert, default: IconInfo };

function Toast({ t, onDismiss }) {
  const timer = useRef(null);
  const remaining = useRef(t.duration);
  const startedAt = useRef(0);

  const start = useCallback(() => {
    if (!t.duration) return;
    startedAt.current = Date.now();
    timer.current = setTimeout(onDismiss, remaining.current);
  }, [t.duration, onDismiss]);

  const pause = useCallback(() => {
    clearTimeout(timer.current);
    remaining.current -= Date.now() - startedAt.current;
  }, []);

  useEffect(() => {
    start();
    return () => clearTimeout(timer.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const Icon = ICONS[t.tone] || IconInfo;
  return (
    <div
      className="toast"
      data-tone={t.tone}
      data-leaving={t.leaving ? "true" : undefined}
      role={t.tone === "error" ? "alert" : "status"}
      aria-live={t.tone === "error" ? "assertive" : "polite"}
      onMouseEnter={pause}
      onMouseLeave={start}
      onFocus={pause}
      onBlur={start}
    >
      <Icon />
      <div style={{ minWidth: 0 }}>
        <div className="toast-title">{t.title}</div>
        {t.description && <div className="toast-desc">{t.description}</div>}
      </div>
      <div className="toast-actions">
        {t.action && (
          <button
            type="button"
            className="btn btn-sm btn-secondary"
            onClick={() => {
              t.action.onClick();
              onDismiss();
            }}
          >
            {t.action.label}
          </button>
        )}
        <button type="button" className="btn btn-sm btn-ghost btn-icon toast-close" aria-label="Dismiss notification" onClick={onDismiss}>
          <IconX />
        </button>
      </div>
    </div>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
