import { useEffect, useState } from "react";
import * as adminApi from "../api/admin";
import { useAuth } from "../AuthContext";

const STATUS_LABEL = { pending: "Pending", approved: "Approved", rejected: "Rejected", suspended: "Suspended" };

export default function AdminUsers() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);

  function refresh() {
    adminApi.listUsers().then((u) => {
      setUsers(u);
      setLoading(false);
    });
  }

  useEffect(refresh, []);

  async function setStatus(userId, status) {
    await adminApi.setUserStatus(userId, status);
    refresh();
  }

  if (loading) return null;

  return (
    <>
      <p className="eyebrow">Admin</p>
      <h1 className="page-title">Access requests</h1>
      <p className="page-sub">{users.filter((u) => u.status === "pending").length} waiting for review</p>

      <table className="admin-table">
        <thead>
          <tr>
            <th>Email</th>
            <th>Role</th>
            <th>Status</th>
            <th>Requested</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <td>{u.email}</td>
              <td><span className="role-badge">{u.role}</span></td>
              <td>{STATUS_LABEL[u.status] || u.status}</td>
              <td>{new Date(u.created_at).toLocaleDateString()}</td>
              <td>
                {u.id === currentUser.id ? (
                  <span style={{ color: "var(--ink-muted)", fontSize: 12.5 }}>This is you</span>
                ) : (
                  <>
                    {u.status !== "approved" && (
                      <button type="button" className="btn btn-gold" onClick={() => setStatus(u.id, "approved")}>Approve</button>
                    )}
                    {u.status !== "rejected" && (
                      <button type="button" className="btn btn-outline" onClick={() => setStatus(u.id, "rejected")}>Reject</button>
                    )}
                    {u.status === "approved" && u.role !== "admin" && (
                      <button type="button" className="btn btn-danger-outline" onClick={() => setStatus(u.id, "suspended")}>Suspend</button>
                    )}
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
