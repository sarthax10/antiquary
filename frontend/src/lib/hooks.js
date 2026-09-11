import { useEffect, useRef, useState } from "react";

/** Sets document.title while the calling page is mounted. */
export function useDocumentTitle(title) {
  useEffect(() => {
    if (!title) return;
    document.title = title === "Antiquary" ? title : `${title} · Antiquary`;
  }, [title]);
}

export function prefersReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

/** True when the event came from somewhere typing should win over single-key shortcuts. */
export function isTypingTarget(target) {
  if (!target || !(target instanceof Element)) return false;
  if (target.closest("input, textarea, select, [contenteditable=''], [contenteditable='true']")) return true;
  return false;
}

/** True if any modal (<dialog open> shown as modal) is currently open. */
export function isModalOpen() {
  return !!document.querySelector("dialog[open]");
}

/**
 * Single-key shortcuts. `map` is { key: handler }, keys compared case-insensitively.
 * Ignores: modifier chords (so Cmd+R still reloads instead of rejecting a story),
 * auto-repeat, typing in fields, and anything while a modal dialog is open.
 */
export function useHotkeys(map, { enabled = true } = {}) {
  const ref = useRef(map);
  ref.current = map;
  useEffect(() => {
    if (!enabled) return undefined;
    function onKeyDown(e) {
      if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey || e.repeat) return;
      if (isTypingTarget(e.target) || isModalOpen()) return;
      const key = e.key === " " ? "space" : e.key.length === 1 ? e.key.toLowerCase() : e.key;
      const handler = ref.current[key];
      if (!handler) return;
      // Space on a focused button/link should activate that control, not the shortcut.
      if (key === "space" && e.target instanceof Element && e.target.closest("button, a, summary, video")) return;
      e.preventDefault();
      handler(e);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [enabled]);
}

/** Becomes true once the element has come within `rootMargin` of the viewport. */
export function useInView(rootMargin = "200px") {
  const ref = useRef(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || inView) return undefined;
    if (typeof IntersectionObserver === "undefined") {
      setInView(true);
      return undefined;
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setInView(true);
          io.disconnect();
        }
      },
      { rootMargin }
    );
    io.observe(el);
    return () => io.disconnect();
  }, [inView, rootMargin]);
  return [ref, inView];
}

/** Ticks every `ms` while `active`, returning Date.now(). */
export function useNow(ms = 1000, active = true) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return undefined;
    const id = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(id);
  }, [ms, active]);
  return now;
}

/** localStorage that never throws (private mode, blocked storage). */
export const safeStorage = {
  get(key) {
    try { return window.localStorage.getItem(key); } catch { return null; }
  },
  set(key, value) {
    try { window.localStorage.setItem(key, value); } catch { /* ignore */ }
  },
};

export const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
export const modKey = isMac ? "⌘" : "Ctrl";
