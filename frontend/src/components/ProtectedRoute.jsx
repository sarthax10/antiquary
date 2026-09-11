import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../AuthContext";
import AppShell from "./AppShell";
import { IconMark } from "./icons";
import { Button } from "./ui";

export function Splash() {
  return (
    <div className="splash" role="status" aria-label="Loading Antiquary">
      <span className="wordmark" aria-hidden="true">
        <IconMark className="wordmark-mark" />
        <span>Antiquary</span>
      </span>
    </div>
  );
}

export function Unreachable({ onRetry }) {
  return (
    <div className="splash">
      <div className="empty" style={{ border: 0 }} role="alert">
        <h2>The studio can’t be reached.</h2>
        <p>The server didn’t respond. It may be restarting after a deploy — try again in a moment.</p>
        <div className="empty-actions">
          <Button variant="primary" onClick={onRetry}>Try again</Button>
        </div>
      </div>
    </div>
  );
}

/** Layout route for every signed-in page: gates on an approved session, then renders the shell. */
export function RequireApproved() {
  const { user, loading, error, retry } = useAuth();
  const location = useLocation();
  if (loading) return <Splash />;
  if (error) return <Unreachable onRetry={retry} />;
  // Remember where the user was headed so Login can send them back there afterwards.
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  if (user.status !== "approved") return <Navigate to="/pending" replace />;
  return <AppShell />;
}

/** Nested guard inside RequireApproved — keeps the same shell mounted across admin pages. */
export function RequireAdmin() {
  const { user } = useAuth();
  if (user?.role !== "admin") return <Navigate to="/create" replace />;
  return <Outlet />;
}
