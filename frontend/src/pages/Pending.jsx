import { Link, Navigate } from "react-router-dom";
import { useAuth } from "../AuthContext";
import AuthLayout from "../components/AuthLayout";
import { IconClock, IconShield } from "../components/icons";
import { Splash } from "../components/ProtectedRoute";
import { Button } from "../components/ui";
import { useDocumentTitle } from "../lib/hooks";

const MESSAGES = {
  pending: ["Almost there.", "Your request is waiting for an admin. Try signing in again once you’ve been approved."],
  rejected: ["Access wasn’t approved.", "An admin declined this request. If you think that’s a mistake, contact the studio’s admin."],
  suspended: ["This account is suspended.", "An admin has paused access for this account."],
};

export default function Pending() {
  useDocumentTitle("Account status");
  const { user, loading, logout } = useAuth();
  if (loading) return <Splash />;
  if (user?.status === "approved") return <Navigate to="/create" replace />;

  const [title, body] = MESSAGES[user?.status] || [
    "Access unavailable.",
    "This account can’t use the studio right now. Pending, rejected and suspended accounts can’t sign in — the sign-in page will tell you which applies.",
  ];
  const Icon = user?.status === "pending" ? IconClock : IconShield;

  return (
    <AuthLayout
      title={
        <div className="auth-head">
          <span className="empty-mark" aria-hidden="true" style={{ margin: "0 0 12px 10px" }}><Icon /></span>
          <h1 id="page-title" className="h1">{title}</h1>
          <p className="muted">{body}</p>
        </div>
      }
    >
      {user ? (
        <Button variant="secondary" size="lg" block onClick={logout}>Sign out</Button>
      ) : (
        <Link to="/login" className="btn btn-primary btn-lg btn-block">Back to sign in</Link>
      )}
    </AuthLayout>
  );
}
