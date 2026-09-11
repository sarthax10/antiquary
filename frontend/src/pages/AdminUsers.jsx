import { useCallback, useEffect, useMemo, useState } from "react";
import * as adminApi from "../api/admin";
import { useAuth } from "../AuthContext";
import { useCounts } from "../CountsContext";
import { useToast } from "../ToastContext";
import { IconCheck, IconMembers, IconShield, IconUndo, IconX } from "../components/icons";
import { Button, ConfirmDialog, EmptyState, ErrorState, PageHeader, Skeleton, Stamp } from "../components/ui";
import { formatDateTime, initial, timeAgo } from "../lib/format";
import { useDocumentTitle } from "../lib/hooks";

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

function MemberActions({ u, isSelf, busy, onSet }) {
  if (isSelf) return <span className="badge badge-outline">You</span>;
  const b = (status) => busy === `${u.id}:${status}`;
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
          <div className="segmented" role="tablist" aria-label="Filter members" style={{ marginBottom: 20 }}>
            {TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                role="tab"
                id={`tab-${t.key}`}
                aria-selected={activeTab === t.key}
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
                        <MemberActions u={u} isSelf={isSelf} busy={busy} onSet={onSet} />
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
    </>
  );
}
