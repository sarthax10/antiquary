import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { listUsers } from "./api/admin";
import { listStories } from "./api/studio";
import { useAuth } from "./AuthContext";

// Shared story lists + nav counts. Any page that mutates a story's status (approve /
// reject / restore) or finishes a generation calls refresh() so the sidebar, tab bar and
// command menu stay in sync without waiting for a route change.
//
// The lists themselves are kept (not just their lengths) because the API already sends
// them in full to compute counts — the command menu reuses them for story search at no
// extra request cost.
const CountsContext = createContext(null);

const EMPTY = { pending: [], approved: [], rejected: [] };

export function CountsProvider({ children }) {
  const { user } = useAuth();
  const [lists, setLists] = useState(EMPTY);
  const [pendingMembers, setPendingMembers] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const inflight = useRef(null);

  const isApproved = user?.status === "approved";
  const isAdmin = isApproved && user?.role === "admin";

  const refresh = useCallback(() => {
    if (!isApproved) return Promise.resolve();
    // Coalesce bursts (e.g. route change + decision in the same tick) into one fetch.
    if (inflight.current) return inflight.current;
    const p = Promise.all([
      listStories("pending"),
      listStories("approved"),
      listStories("rejected"),
      isAdmin ? listUsers("pending").catch(() => null) : Promise.resolve(null),
    ])
      .then(([pending, approved, rejected, members]) => {
        setLists({ pending, approved, rejected });
        if (members) setPendingMembers(members.length);
        setLoaded(true);
      })
      .catch(() => {
        /* counts are ambient — a failed refresh keeps the last known values */
      })
      .finally(() => {
        inflight.current = null;
      });
    inflight.current = p;
    return p;
  }, [isApproved, isAdmin]);

  useEffect(() => {
    if (isApproved) refresh();
    else {
      setLists(EMPTY);
      setPendingMembers(0);
      setLoaded(false);
    }
  }, [isApproved, refresh]);

  const value = useMemo(
    () => ({
      lists,
      loaded,
      counts: {
        pending: lists.pending.length,
        approved: lists.approved.length,
        rejected: lists.rejected.length,
        members: pendingMembers,
      },
      refresh,
    }),
    [lists, loaded, pendingMembers, refresh]
  );

  return <CountsContext.Provider value={value}>{children}</CountsContext.Provider>;
}

export function useCounts() {
  const ctx = useContext(CountsContext);
  if (!ctx) throw new Error("useCounts must be used within CountsProvider");
  return ctx;
}
