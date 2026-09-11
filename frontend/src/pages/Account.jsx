import { useState } from "react";
import * as authApi from "../api/auth";
import { useAuth } from "../AuthContext";
import { ApiError } from "../api/client";
import { useToast } from "../ToastContext";
import { IconAlert } from "../components/icons";
import { Button, PageHeader, PasswordField } from "../components/ui";
import { initial } from "../lib/format";
import { useDocumentTitle } from "../lib/hooks";

// Mirrors app/auth/service.py MIN_PASSWORD_LENGTH — the server remains the authority.
const MIN_PASSWORD = 10;

export default function Account() {
  useDocumentTitle("Account");
  const { user } = useAuth();
  const { toast } = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const longEnough = next.length >= MIN_PASSWORD;
  const mismatch = confirm.length > 0 && confirm !== next;

  async function submit(e) {
    e.preventDefault();
    if (submitting) return;
    setError(null);
    if (!longEnough) return setError(`New password must be at least ${MIN_PASSWORD} characters.`);
    if (mismatch) return setError("New passwords don’t match.");
    setSubmitting(true);
    try {
      await authApi.changePassword(current, next);
      setCurrent("");
      setNext("");
      setConfirm("");
      toast({ tone: "success", title: "Password updated" });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn’t reach the studio. Check your connection and try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <PageHeader eyebrow="Account" title="Your account" description="Manage your own sign-in credentials." />

      <section className="panel" style={{ maxWidth: 480 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
          <span className="avatar" aria-hidden="true">{initial(user?.email)}</span>
          <div style={{ minWidth: 0 }}>
            <div className="account-email" style={{ fontSize: 14 }}>{user?.email}</div>
            <div className="account-role">{user?.role === "admin" ? "Admin" : "Member"}</div>
          </div>
        </div>

        <h2 className="h2" style={{ fontSize: 16, marginBottom: 12 }}>Change password</h2>
        {error && (
          <div className="callout callout-error" role="alert" style={{ marginBottom: 12 }}>
            <IconAlert />
            <div>{error}</div>
            <span />
          </div>
        )}
        <form onSubmit={submit} className="auth-form">
          <PasswordField
            label="Current password"
            name="current-password"
            autoComplete="current-password"
            required
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
          <PasswordField
            label="New password"
            name="new-password"
            autoComplete="new-password"
            required
            minLength={MIN_PASSWORD}
            value={next}
            onChange={(e) => setNext(e.target.value)}
            hint={longEnough ? "Long enough" : `At least ${MIN_PASSWORD} characters${next ? ` · ${MIN_PASSWORD - next.length} to go` : ""}`}
            hintOk={longEnough}
          />
          <PasswordField
            label="Confirm new password"
            name="confirm-password"
            autoComplete="new-password"
            required
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            error={mismatch ? "Doesn’t match the new password above." : null}
          />
          <Button type="submit" variant="primary" loading={submitting}>Update password</Button>
        </form>
      </section>
    </>
  );
}
