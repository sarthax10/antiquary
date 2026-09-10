import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../AuthContext";
import Sidebar from "./Sidebar";

export function RequireApproved() {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  if (user.status !== "approved") return <Navigate to="/pending" replace />;

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="main"><div className="main-inner"><Outlet /></div></main>
    </div>
  );
}

export function RequireAdmin() {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== "admin") return <Navigate to="/create" replace />;

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="main"><div className="main-inner"><Outlet /></div></main>
    </div>
  );
}
