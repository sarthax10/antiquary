// Small, dependency-free formatting helpers shared across pages.

export function formatDuration(seconds) {
  if (seconds == null || Number.isNaN(Number(seconds))) return "—";
  const s = Math.round(Number(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

const rtf = typeof Intl !== "undefined" && Intl.RelativeTimeFormat
  ? new Intl.RelativeTimeFormat(undefined, { numeric: "auto" })
  : null;

const UNITS = [
  ["year", 365 * 24 * 3600],
  ["month", 30 * 24 * 3600],
  ["week", 7 * 24 * 3600],
  ["day", 24 * 3600],
  ["hour", 3600],
  ["minute", 60],
];

/** "3 hours ago", "yesterday", "just now". Accepts an ISO string, Date, or epoch ms. */
export function timeAgo(value) {
  if (!value) return "—";
  const date = value instanceof Date ? value : new Date(value);
  const diff = (date.getTime() - Date.now()) / 1000;
  const abs = Math.abs(diff);
  if (abs < 45) return "just now";
  for (const [unit, secs] of UNITS) {
    if (abs >= secs || unit === "minute") {
      const n = Math.round(diff / secs);
      return rtf ? rtf.format(n, unit) : `${Math.abs(n)} ${unit}${Math.abs(n) === 1 ? "" : "s"} ago`;
    }
  }
  return "—";
}

export function formatDateTime(value) {
  if (!value) return "—";
  return new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function formatDate(value) {
  if (!value) return "—";
  return new Date(value).toLocaleDateString(undefined, { dateStyle: "medium" });
}

export function plural(n, one, many = `${one}s`) {
  return `${n} ${n === 1 ? one : many}`;
}

export function pad2(n) {
  return String(n).padStart(2, "0");
}

export function wordCount(text) {
  return (text || "").trim().split(/\s+/).filter(Boolean).length;
}

/** Claim counts with safe defaults — the API always sends these three keys, but a
 *  story with an empty fact_check shouldn't crash a page. */
export function claimTotals(story) {
  const c = story?.claim_counts || {};
  const verified = c.verified || 0;
  const uncertain = c.uncertain || 0;
  const flagged = c.false || 0;
  return { verified, uncertain, flagged, total: verified + uncertain + flagged };
}

export function initial(email) {
  return (email || "?").trim().charAt(0) || "?";
}
