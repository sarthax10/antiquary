import { useAuth } from "../AuthContext";

export default function Pending() {
  const { user, logout } = useAuth();
  const status = user?.status;

  const messages = {
    pending: "Your request is awaiting admin approval. Check back soon.",
    rejected: "Your access request was not approved.",
    suspended: "Your account has been suspended.",
  };

  return (
    <div className="auth-shell">
      <div className="auth-card" style={{ textAlign: "center" }}>
        <div className="brand-word" style={{ margin: "0 auto 20px" }}>Antiquary</div>
        <h1>{status === "pending" ? "Almost there" : "Access unavailable"}</h1>
        <p className="sub">{messages[status] || "Your account can't access the archive right now."}</p>
        <button type="button" className="btn btn-outline" onClick={logout}>Sign out</button>
      </div>
    </div>
  );
}
