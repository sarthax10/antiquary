import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import * as studioApi from "./api/studio";
import { useAuth } from "./AuthContext";
import { useCounts } from "./CountsContext";
import { useToast } from "./ToastContext";

// Kept in sync with app/generation/job_manager.py's STAGES — real pipeline steps reported
// by the pipeline subprocess itself, never a simulated timer.
export const STAGES = [
  { key: "writing", label: "Writing the story", detail: "Drafting a title, hook and narration from your prompt." },
  { key: "fact_checking", label: "Fact-checking claims", detail: "A second pass lists each claim and flags doubts." },
  { key: "sourcing_visuals", label: "Sourcing visuals", detail: "Pulling archival imagery from Wikimedia Commons and Pexels." },
  { key: "recording_narration", label: "Recording narration", detail: "Synthesising the voice-over." },
  { key: "generating_captions", label: "Generating captions", detail: "Transcribing the narration into timed captions." },
  { key: "rendering", label: "Rendering the film", detail: "Cutting it all together into a 9:16 video." },
];

export function stageIndex(stageKey) {
  return STAGES.findIndex((s) => s.key === stageKey);
}

const RUNNING_POLL_MS = 2500;
const IDLE_POLL_MS = 20000;

// One generation runs globally at a time (see CLAUDE.md), so its status is app-wide
// state: the sidebar, the mobile top bar and the Create page all read it from here, and a
// finished render announces itself wherever the user happens to be.
const GenerationContext = createContext(null);

export function GenerationProvider({ children }) {
  const { user } = useAuth();
  const { refresh: refreshCounts } = useCounts();
  const { toast } = useToast();
  const navigate = useNavigate();
  const navigateRef = useRef(navigate);
  navigateRef.current = navigate;
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const prev = useRef(null);
  const listeners = useRef(new Set());
  const enabled = user?.status === "approved";

  const apply = useCallback(
    (next) => {
      const before = prev.current;
      prev.current = next;
      setStatus((cur) => (JSON.stringify(cur) === JSON.stringify(next) ? cur : next));
      if (before?.status === "running" && next.status !== "running") {
        refreshCounts();
        listeners.current.forEach((fn) => fn(next));
        if (next.status === "done") {
          toast({
            tone: "success",
            title: "A new story is ready for review",
            description: next.topic ? `“${next.topic}”` : "The archive picked this one.",
            duration: 9000,
            action: { label: "Review", onClick: () => navigateRef.current(next.story_id ? `/review?item=${next.story_id}` : "/review") },
          });
        } else if (next.status === "error") {
          toast({ tone: "error", title: "Generation failed", description: "Details are on the Create page.", duration: 9000, action: { label: "View", onClick: () => navigateRef.current("/create") } });
        }
      }
    },
    [refreshCounts, toast]
  );

  const refresh = useCallback(async () => {
    try {
      const next = await studioApi.generationStatus();
      setError(null);
      apply(next);
      return next;
    } catch (err) {
      setError(err);
      return null;
    }
  }, [apply]);

  // Poll quickly while running, slowly while idle (another member may start a job), and
  // not at all while the tab is hidden.
  useEffect(() => {
    if (!enabled) {
      prev.current = null;
      setStatus(null);
      return undefined;
    }
    let timer;
    let cancelled = false;
    const loop = async () => {
      if (cancelled) return;
      const next = document.hidden ? prev.current : await refresh();
      if (cancelled) return;
      timer = setTimeout(loop, next?.status === "running" ? RUNNING_POLL_MS : IDLE_POLL_MS);
    };
    loop();
    const onVisible = () => {
      if (!document.hidden) {
        clearTimeout(timer);
        loop();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [enabled, refresh, status?.status]);

  const start = useCallback(
    async (topic) => {
      const res = await studioApi.startGeneration(topic);
      await refresh();
      return res;
    },
    [refresh]
  );

  const cancel = useCallback(async () => {
    const res = await studioApi.cancelGeneration();
    await refresh();
    return res;
  }, [refresh]);

  /** Subscribe to the running → finished transition. Returns an unsubscribe fn. */
  const onFinish = useCallback((fn) => {
    listeners.current.add(fn);
    return () => listeners.current.delete(fn);
  }, []);

  const value = useMemo(
    () => ({ status, error, running: status?.status === "running", refresh, start, cancel, onFinish }),
    [status, error, refresh, start, cancel, onFinish]
  );

  return <GenerationContext.Provider value={value}>{children}</GenerationContext.Provider>;
}

export function useGeneration() {
  const ctx = useContext(GenerationContext);
  if (!ctx) throw new Error("useGeneration must be used within GenerationProvider");
  return ctx;
}
