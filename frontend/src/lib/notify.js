// Desktop notifications for "your story is ready" — the in-app toast already covers the
// case where the studio tab is open and focused, so this only fires when it isn't (the
// whole point of the OS-level notification), and does nothing at all where the browser
// doesn't support it or the user hasn't granted permission.
const MARK = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Crect width='24' height='24' fill='%230b0a08'/%3E%3Cpath d='M12 4l2.1 6.2L20.5 12l-6.4 2.1L12 20.5l-2.1-6.4L3.5 12l6.4-1.8L12 4z' fill='%23eba54a'/%3E%3C/svg%3E";

export function notificationsSupported() {
  return typeof window !== "undefined" && "Notification" in window;
}

export function notificationPermission() {
  return notificationsSupported() ? Notification.permission : "unsupported";
}

/** Ask once, from a real user gesture (a click) — browsers require this, and silently
 * ignore repeat requests once the user has already granted or denied it. */
export function requestNotificationPermission() {
  if (!notificationsSupported() || Notification.permission !== "default") return;
  Notification.requestPermission().catch(() => {});
}

/** Shows a native notification if permitted, and only while the tab isn't the one the
 * user is looking at — otherwise the in-app toast for the same event is enough. Returns
 * the Notification instance (or null) so a caller can wire onclick. */
export function notify(title, { body, tag, onClick } = {}) {
  if (!notificationsSupported() || Notification.permission !== "granted" || !document.hidden) return null;
  try {
    const n = new Notification(title, { body, tag, icon: MARK, badge: MARK });
    if (onClick) {
      n.onclick = () => {
        window.focus();
        onClick();
        n.close();
      };
    }
    return n;
  } catch {
    return null;
  }
}
