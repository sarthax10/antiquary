import { createContext, useCallback, useContext, useState } from "react";
import { listStories } from "./api/studio";

// Sidebar nav-counts, shared so any page that mutates a story's status (approve/reject/
// restore) or finishes a generation can trigger a refresh without needing a route change
// to happen to notice — Sidebar previously only refetched on location.pathname change,
// which missed "approve, stay on /review for the next item" entirely.
const CountsContext = createContext(null);

export function CountsProvider({ children }) {
  const [counts, setCounts] = useState({ pending: 0, approved: 0, rejected: 0 });

  const refresh = useCallback(() => {
    Promise.all([listStories("pending"), listStories("approved"), listStories("rejected")]).then(
      ([pending, approved, rejected]) => {
        setCounts({ pending: pending.length, approved: approved.length, rejected: rejected.length });
      }
    );
  }, []);

  return <CountsContext.Provider value={{ counts, refresh }}>{children}</CountsContext.Provider>;
}

export function useCounts() {
  const ctx = useContext(CountsContext);
  if (!ctx) throw new Error("useCounts must be used within CountsProvider");
  return ctx;
}
