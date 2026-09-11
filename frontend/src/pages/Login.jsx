import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../AuthContext";
import { ApiError } from "../api/client";
import AuthLayout from "../components/AuthLayout";
import { IconAlert, IconCheck } from "../components/icons";
import { Splash } from "../components/ProtectedRoute";
import { Button, PasswordField, TextField } from "../components/ui";
import { useDocumentTitle } from "../lib/hooks";

export default function Login() {
  useDocumentTitle("Sign in");
  const { user, loading, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState(location.state?.email || "");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const errorRef = useRef(null);

  const from = location.state?.from || "/create";
  const justSignedUp = location.state?.justSignedUp;

  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  if (loading) return <Splash />;
  // Already signed in — don't show a login form to someone who's in.
  if (user?.status === "approved") return <Navigate to={from} replace />;

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn’t reach the studio. Check your connection and try again.");
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      title={
        <div className="auth-head">
          <h1 id="page-title" className="h1">Welcome back.</h1>
          <p className="muted">Sign in to the studio.</p>
        </div>
      }
    >
      {justSignedUp && !error && (
        <div className="callout callout-success" role="status">
          <IconCheck />
          <div>
            <div className="callout-title">Request sent</div>
            <span>An admin will review it. You’ll be able to sign in here as soon as you’re approved.</span>
          </div>
          <span />
        </div>
      )}
      {error && (
        <div className="callout callout-error" role="alert" tabIndex={-1} ref={errorRef}>
          <IconAlert />
          <div>{error}</div>
          <span />
        </div>
      )}
      <form onSubmit={handleSubmit} className="auth-form" noValidate={false}>
        <TextField label="Email" type="email" name="email" autoComplete="email" inputMode="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoFocus={!email} />
        <PasswordField label="Password" name="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} autoFocus={!!email} />
        <Button type="submit" variant="primary" size="lg" block loading={submitting}>
          Sign in
        </Button>
      </form>
      <p className="auth-switch">
        New here? <Link to="/signup" className="link">Request access</Link>
      </p>
    </AuthLayout>
  );
}
