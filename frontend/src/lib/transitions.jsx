import { flushSync } from "react-dom";
import { Link, useNavigate } from "react-router-dom";
import { prefersReducedMotion } from "./hooks";

/**
 * Navigate inside a View Transition when the browser supports it, so elements sharing a
 * view-transition-name (a story's poster and its player) morph between pages. Falls back
 * to a plain navigation everywhere else, and under prefers-reduced-motion.
 *
 * Implemented here (~20 lines) rather than by switching to React Router's data router,
 * whose <Link viewTransition> would have added ~50 kB of router code for this one effect.
 */
export function useTransitionNavigate() {
  const navigate = useNavigate();
  return (to, options) => {
    if (typeof document === "undefined" || !document.startViewTransition || prefersReducedMotion()) {
      navigate(to, options);
      return;
    }
    document.startViewTransition(() => {
      flushSync(() => navigate(to, options));
    });
  };
}

export function TransitionLink({ to, onClick, ...rest }) {
  const go = useTransitionNavigate();
  return (
    <Link
      to={to}
      onClick={(e) => {
        onClick?.(e);
        // Respect new-tab / modified clicks and anything already handled.
        if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        go(to);
      }}
      {...rest}
    />
  );
}
