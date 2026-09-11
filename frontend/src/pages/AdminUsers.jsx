import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import * as adminApi from "../api/admin";
import { ApiError } from "../api/client";
import { useAuth } from "../AuthContext";
import { useCounts } from "../CountsContext";
import { useToast } from "../ToastContext";
import { IconAlert, IconCheck, IconMembers, IconRefresh, IconShield, IconUndo, IconX } from "../components/icons";
import { Button, ConfirmDialog, Dialog, EmptyState, ErrorState, PageHeader, PasswordField, Skeleton, Stamp } from "../components/ui";
import { formatDateTime, initial, timeAgo } from "../lib/format";
import { useDocumentTitle } from "../lib/hooks";

// Mirrors app/auth/service.py MIN_PASSWORD_LENGTH.
const MIN_PASSWORD = 10;

function ResetPasswordDialog({ user, onClose, onDone }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const titleId = useId();
  const ref = useRef(null);

  useEffect(() => {
    setPassword("");
    setError(null);
  }, [user]);

  async function submit(e) {
    e.preventDefault();
    if (submitting) return;
    setError(null);
    setSubmitting(true);
    try {
      const updated = await adminApi.resetPassword(user.id, password);
      onDone(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn’t reach the studio.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={!!user} onClose={onClose} labelledBy={titleId} initialFocusRef={ref}>
      <form onSubmit={submit} className="auth-form" style={{ padding: 20, minWidth: 320 }}>
        <h2 id={titleId} className="h2" style={{ fontSize: 16, marginBottom: 4 }}>Reset password</h2>
        <p className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
          Sets a new password for {user?.email} directly — share it with them yourself, there’s no email flow.
        </p>
        {error && (
          <div className="callout callout-error" role="alert" style={{ marginBottom: 12 }}>
            <IconAlert />
            <div>{error}</div>
            <span />
          </div>
        )}
        <PasswordField
          ref={ref}
          label="New password"
          name="new-password"
          autoComplete="new-password"
          required
          minLength={MIN_PASSWORD}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          hint={`At least ${MIN_PASSWORD} characters`}
        />
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" loading={submitting}>Set password</Button>
        </div>
      </form>
    </Dialog>
  );
}

const TABS = [
  { key: "pending", label: "Requests", match: (u) => u.status === "pending" },
  { key: "approved", label: "Active", match: (u) => u.status === "approved" },
  { key: "blocked", label: "Rejected & suspended", match: (u) => u.status === "rejected" || u.status === "suspended" },
  { key: "all", label: "Everyone", match: () => true },
];

const CONFIRM = {
  suspended: {
    title: "Suspend this member?",
    body: (u) => `${u.email} will be signed out on their next request and can’t use the studio until reinstated.`,
    label: "Suspend",
  },
  rejected: {
    title: "Revoke access?",
    body: (u) => `${u.email} loses access immediately and moves to Rejected. You can approve them again later.`,
    label: "Revoke access",
  },
};

const SUCCESS = { approved: "Access approved", rejected: "Request rejected", suspended: "Member suspended" };

function MemberActions({ u, isSelf, busy, onSet, onToggleRole, onResetPassword }) {
  const b = (status) => busy === `${u.id}:${status}`;
  const extra = u.status === "approved" && !isSelf && (
    <>
      <Button size="sm" variant="ghost" icon={IconShield} loading={b("role")} onClick={() => onToggleRole(u)}>
        {u.role === "admin" ? "Remove admin" : "Make admin"}
      </Button>
      <Button size="sm" variant="ghost" icon={IconRefresh} onClick={() => onResetPassword(u)}>Reset password</Button>
    </>
  );
  if (isSelf) return <span className="badge badge-outline">You</span>;
  switch (u.status) {
    case "pending":
      return (
        <>
          <Button size="sm" variant="ghost" icon={IconX} loading={b("rejected")} onClick={() => onSet(u, "rejected")}>Reject</Button>
          <Button size="sm" variant="primary" icon={IconCheck} loading={b("approved")} onClick={() => onSet(u, "approved")}>Approve</Button>
        </>
      );
    case "approved":
      return (
        <>
          {extra}
          <Button size="sm" variant="ghost" loading={b("rejected")} onClick={() => onSet(u, "rejected", true)}>Revoke</Button>
          {u.role !== "admin" && <Button size="sm" variant="danger" loading={b("suspended")} onClick={() => onSet(u, "suspended", true)}>Suspend</Button>}
        </>
      );
    case "suspended":
      return <Button size="sm" variant="secondary" icon={IconUndo} loading={b("approved")} onClick={() => onSet(u, "approved")}>Reinstate</Button>;
    case "rejected":
      return <Button size="sm" variant="secondary" icon={IconCheck} loading={b("approved")} onClick={() => onSet(u, "approved")}>Approve</Button>;
    default:
      return null;
  }
}

export default function AdminUsers() {
  useDocumentTitle("Members");
  const { user: currentUser } = useAuth();
  const { refresh: refreshCounts } = useCounts();
  const { toast } = useToast();
  const [users, setUsers] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState(null);
  const [busy, setBusy] = useState(null);
  const [confirm, setConfirm] = useState(null); // { user, status }
  const [resetTarget, setResetTarget] = useState(null); // user whose password is being reset

  const load = useCallback(() => {
    setError(null);
    adminApi.listUsers().then(setUsers).catch(setError);
  }, []);
  useEffect(load, [load]);

  const byTab = useMemo(() => Object.fromEntries(TABS.map((t) => [t.key, (users || []).filter(t.match)])), [users]);
  // Default to the actionable tab when there's something to act on.
  const activeTab = tab || (byTab.pending?.length ? "pending" : "all");
  const rows = byTab[activeTab] || [];

  async function apply(u, status) {
    const previous = u.status;
    setBusy(`${u.id}:${status}`);
    try {
      const updated = await adminApi.setUserStatus(u.id, status);
      setUsers((list) => list.map((x) => (x.id === u.id ? { ...x, ...updated } : x)));
      refreshCounts();
      toast({
        tone: "success",
        title: SUCCESS[status] || "Updated",
        description: u.email,
        action: previous && previous !== status ? {
          label: "Undo",
          onClick: async () => {
            try {
              const reverted = await adminApi.setUserStatus(u.id, previous);
              setUsers((list) => list.map((x) => (x.id === u.id ? { ...x, ...reverted } : x)));
              refreshCounts();
            } catch (err) {
              toast({ tone: "error", title: "Couldn’t undo", description: err.message });
            }
          },
        } : undefined,
      });
    } catch (err) {
      toast({ tone: "error", title: "Change not saved", description: err.message });
    } finally {
      setBusy(null);
      setConfirm(null);
    }
  }

  function onSet(u, status, needsConfirm) {
    if (needsConfirm) setConfirm({ user: u, status });
    else apply(u, status);
  }

  async function toggleRole(u) {
    const role = u.role === "admin" ? "user" : "admin";
    setBusy(`${u.id}:role`);
    try {
      const updated = await adminApi.setUserRole(u.id, role);
      setUsers((list) => list.map((x) => (x.id === u.id ? { ...x, ...updated } : x)));
      toast({ tone: "success", title: role === "admin" ? "Now an admin" : "Admin removed", description: u.email });
    } catch (err) {
      toast({ tone: "error", title: "Change not saved", description: err.message });
    } finally {
      setBusy(null);
    }
  }

  function onPasswordReset(updated) {
    setUsers((list) => list.map((x) => (x.id === updated.id ? { ...x, ...updated } : x)));
    toast({ tone: "success", title: "Password reset", description: updated.email });
    setResetTarget(null);
  }

  const pendingCount = byTab.pending?.length || 0;

  return (
    <>
      <PageHeader
        eyebrow="Admin"
        index="05"
        title="Members"
        description={
          users === null
            ? "Everyone who can use the studio, and everyone asking to."
            : pendingCount
              ? `${pendingCount} ${pendingCount === 1 ? "person is" : "people are"} waiting for access. New accounts can’t sign in until approved.`
              : "No one is waiting. New accounts can’t sign in until an admin approves them."
        }
      />

      {error ? (
        <ErrorState title="Members didn’t load" error={error} onRetry={load} />
      ) : users === null ? (
        <div className="members" aria-busy="true">
          {Array.from({ length: 4 }, (_, i) => <Skeleton key={i} height={64} radius={10} style={{ marginBottom: 8 }} />)}
        </div>
      ) : (
        <>
          <div
            className="segmented"
            role="tablist"
            aria-label="Filter members"
            style={{ marginBottom: 20 }}
            onKeyDown={(e) => {
              // WAI-ARIA tabs pattern: arrows move between tabs.
              if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
              const i = TABS.findIndex((t) => t.key === activeTab);
              const next = TABS[(i + (e.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length];
              setTab(next.key);
              e.currentTarget.querySelector(`#tab-${next.key}`)?.focus();
            }}
          >
            {TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                role="tab"
                id={`tab-${t.key}`}
                aria-selected={activeTab === t.key}
                tabIndex={activeTab === t.key ? 0 : -1}
                aria-controls="members-panel"
                onClick={() => setTab(t.key)}
              >
                {t.label}
                <span className="count">{byTab[t.key].length}</span>
              </button>
            ))}
          </div>

          <div id="members-panel" role="tabpanel" aria-labelledby={`tab-${activeTab}`}>
            {rows.length === 0 ? (
              <EmptyState icon={activeTab === "pending" ? IconShield : IconMembers} title={activeTab === "pending" ? "No requests waiting." : "No one here."}>
                {activeTab === "pending" ? "When someone requests access, they’ll appear here for approval." : "Nobody matches this filter right now."}
              </EmptyState>
            ) : (
              <ul className="members stagger">
                {rows.map((u, i) => {
                  const isSelf = u.id === currentUser.id;
                  return (
                    <li key={u.id} className="member" style={{ "--i": i }} data-status={u.status}>
                      <span className="avatar" aria-hidden="true">{initial(u.email)}</span>
                      <div className="member-id">
                        <span className="member-email">{u.email}</span>
                        <span className="meta" title={formatDateTime(u.created_at)}>
                          {u.status === "pending" ? "Requested" : "Joined"} {timeAgo(u.created_at)}
                          {u.role === "admin" && <> · <span style={{ color: "var(--tungsten)" }}>Admin</span></>}
                        </span>
                      </div>
                      <Stamp status={u.status}>{u.status}</Stamp>
                      <div className="member-actions">
                        <MemberActions u={u} isSelf={isSelf} busy={busy} onSet={onSet} onToggleRole={toggleRole} onResetPassword={setResetTarget} />
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </>
      )}

      <ConfirmDialog
        open={!!confirm}
        title={confirm ? CONFIRM[confirm.status]?.title : ""}
        confirmLabel={confirm ? CONFIRM[confirm.status]?.label : ""}
        tone="danger"
        busy={!!busy}
        onConfirm={() => apply(confirm.user, confirm.status)}
        onCancel={() => setConfirm(null)}
      >
        {confirm ? CONFIRM[confirm.status]?.body(confirm.user) : ""}
      </ConfirmDialog>

      <ResetPasswordDialog user={resetTarget} onClose={() => setResetTarget(null)} onDone={onPasswordReset} />
    </>
  );
}
