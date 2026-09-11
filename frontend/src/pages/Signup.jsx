import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import * as authApi from "../api/auth";
import { useAuth } from "../AuthContext";
import { ApiError } from "../api/client";
import AuthLayout from "../components/AuthLayout";
import { IconAlert } from "../components/icons";
import { Button, PasswordField, TextField } from "../components/ui";
import { useDocumentTitle } from "../lib/hooks";

// Mirrors app/auth/service.py MIN_PASSWORD_LENGTH — the server remains the authority.
const MIN_PASSWORD = 10;

export default function Signup() {
  useDocumentTitle("Request access");
  const { user } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [touchedConfirm, setTouchedConfirm] = useState(false);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const errorRef = useRef(null);

  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  if (user?.status === "approved") return <Navigate to="/create" replace />;

  const longEnough = password.length >= MIN_PASSWORD;
  const mismatch = (touchedConfirm || confirm.length >= password.length) && confirm.length > 0 && confirm !== password;

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    if (!longEnough) return setError(`Password must be at least ${MIN_PASSWORD} characters.`);
    if (password !== confirm) {
      setTouchedConfirm(true);
      return setError("Passwords don’t match.");
    }
    setSubmitting(true);
    try {
      await authApi.signup(email, password);
      navigate("/login", { state: { justSignedUp: true, email } });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn’t reach the studio. Check your connection and try again.");
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      title={
        <div className="auth-head">
          <h1 id="page-title" className="h1">Request access.</h1>
          <p className="muted">An admin reviews every request. You can sign in once you’re approved.</p>
        </div>
      }
    >
      {error && (
        <div className="callout callout-error" role="alert" tabIndex={-1} ref={errorRef}>
          <IconAlert />
          <div>{error}</div>
          <span />
        </div>
      )}
      <form onSubmit={handleSubmit} className="auth-form">
        <TextField label="Email" type="email" name="email" autoComplete="email" inputMode="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
        <PasswordField
          label="Password"
          name="new-password"
          autoComplete="new-password"
          required
          minLength={MIN_PASSWORD}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          hint={longEnough ? "Long enough" : `At least ${MIN_PASSWORD} characters${password ? ` · ${MIN_PASSWORD - password.length} to go` : ""}`}
          hintOk={longEnough}
        />
        <PasswordField
          label="Confirm password"
          name="confirm-password"
          autoComplete="new-password"
          required
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          onBlur={() => setTouchedConfirm(true)}
          error={mismatch ? "Doesn’t match the password above." : null}
        />
        <Button type="submit" variant="primary" size="lg" block loading={submitting}>
          Request access
        </Button>
      </form>
      <p className="auth-switch">
        Already approved? <Link to="/login" className="link">Sign in</Link>
      </p>
    </AuthLayout>
  );
}
