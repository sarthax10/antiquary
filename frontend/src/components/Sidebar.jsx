import { useEffect } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useAuth } from "../AuthContext";
import { useCounts } from "../CountsContext";
import { IconArchive, IconConnections, IconCreate, IconLibrary, IconReview } from "./icons";

const NAV_ITEMS = [
  { to: "/create", label: "Create", icon: IconCreate },
  { to: "/review", label: "Review", icon: IconReview, countKey: "pending" },
  { to: "/library", label: "Library", icon: IconLibrary, countKey: "approved" },
  { to: "/archive", label: "Archive", icon: IconArchive, countKey: "rejected" },
  { to: "/connections", label: "Connections", icon: IconConnections },
];

export default function Sidebar() {
  const { counts, refresh } = useCounts();
  const location = useLocation();
  const { user, logout } = useAuth();

  useEffect(refresh, [location.pathname, refresh]);

  return (
    <nav className="rail" aria-label="Main navigation">
      <NavLink to="/create" className="brand-word">Antiquary</NavLink>
      <div className="nav">
        {NAV_ITEMS.map(({ to, label, icon: Icon, countKey }) => (
          <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "active" : "")}>
            <Icon />
            <span className="label">{label}</span>
            {countKey && <span className="nav-count">{counts[countKey]}</span>}
          </NavLink>
        ))}
        {user?.role === "admin" && (
          <NavLink to="/admin/users" className={({ isActive }) => (isActive ? "active" : "")}>
            <span className="label">Admin</span>
          </NavLink>
        )}
      </div>
      <button type="button" className="btn btn-ghost" style={{ marginTop: 12 }} onClick={logout}>
        Sign out
      </button>
      <div className="rail-foot">Nothing here posts anywhere by itself.</div>
    </nav>
  );
}
