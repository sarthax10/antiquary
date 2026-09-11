import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../AuthContext";
import { useCounts } from "../CountsContext";
import { initial } from "../lib/format";
import { isModalOpen, isTypingTarget, modKey } from "../lib/hooks";
import CommandMenu from "./CommandMenu";
import ErrorBoundary from "./ErrorBoundary";
import { GenerationPill, GenerationWidget } from "./GenerationIndicator";
import { IconDots, IconLogout, IconMark, IconSearch, IconSparkle } from "./icons";
import { ADMIN_ITEMS, NAV_ITEMS } from "./nav";
import ShortcutsDialog from "./ShortcutsDialog";
import { Button, Dialog, Kbd } from "./ui";

function Wordmark() {
  return (
    <Link to="/create" className="wordmark" aria-label="Antiquary — go to Create">
      <IconMark className="wordmark-mark" />
      <span>Antiquary</span>
    </Link>
  );
}

function NavCount({ n, attention }) {
  if (n == null) return null;
  return (
    <span className="nav-count" data-attention={attention && n > 0 ? "true" : undefined} aria-label={`${n} items`}>
      {n}
    </span>
  );
}

function Sidebar({ onOpenCommand }) {
  const { user, logout } = useAuth();
  const { counts } = useCounts();
  const isAdmin = user?.role === "admin";

  return (
    <aside className="sidebar" aria-label="Sidebar">
      <Wordmark />

      <div className="sidebar-cta">
        <GenerationWidget />
      </div>

      <nav className="nav-section" aria-label="Studio">
        <span className="label">Studio</span>
        {NAV_ITEMS.map(({ to, label, icon: Icon, countKey, attention, index }) => (
          <NavLink key={to} to={to} className="nav-link">
            <Icon />
            <span>{label}</span>
            {countKey ? <NavCount n={counts[countKey]} attention={attention} /> : <span className="nav-index">{index}</span>}
          </NavLink>
        ))}
      </nav>

      {isAdmin && (
        <nav className="nav-section" aria-label="Admin">
          <span className="label">Admin</span>
          {ADMIN_ITEMS.map(({ to, label, icon: Icon, countKey, attention }) => (
            <NavLink key={to} to={to} className="nav-link">
              <Icon />
              <span>{label}</span>
              {counts[countKey] > 0 && <NavCount n={counts[countKey]} attention={attention} />}
            </NavLink>
          ))}
        </nav>
      )}

      <div className="sidebar-foot">
        <button type="button" className="command-trigger" onClick={onOpenCommand}>
          <IconSearch />
          <span>Search</span>
          <span className="kbd-group" aria-hidden="true"><Kbd>{modKey}</Kbd><Kbd>K</Kbd></span>
        </button>
        <div className="account">
          <span className="avatar" aria-hidden="true">{initial(user?.email)}</span>
          <div className="account-id">
            <div className="account-email" title={user?.email}>{user?.email}</div>
            <div className="account-role">{isAdmin ? "Admin" : "Member"}</div>
          </div>
          <button type="button" className="btn btn-ghost btn-sm btn-icon" onClick={logout} aria-label="Sign out" data-tip="Sign out">
            <IconLogout />
          </button>
        </div>
        <p className="sidebar-note">Nothing here posts anywhere by itself.</p>
      </div>
    </aside>
  );
}

function TopBar({ onOpenCommand, onOpenAccount }) {
  const { user } = useAuth();
  return (
    <header className="topbar">
      <Wordmark />
      <div className="topbar-actions">
        <GenerationPill />
        <Button variant="ghost" icon={IconSearch} onClick={onOpenCommand} aria-label="Search and commands" />
        <button type="button" className="btn btn-ghost btn-icon" onClick={onOpenAccount} aria-label="Account menu">
          <span className="avatar avatar-sm" aria-hidden="true">{initial(user?.email)}</span>
        </button>
      </div>
    </header>
  );
}

function TabBar() {
  const { counts } = useCounts();
  return (
    <nav className="tabbar" aria-label="Primary">
      {NAV_ITEMS.map(({ to, label, icon: Icon, countKey, attention }) => (
        <NavLink key={to} to={to} className="tab">
          <Icon />
          <span>{label}</span>
          {countKey && attention && counts[countKey] > 0 && (
            <span className="tab-badge" aria-label={`${counts[countKey]} waiting`}>{counts[countKey] > 99 ? "99+" : counts[countKey]}</span>
          )}
        </NavLink>
      ))}
    </nav>
  );
}

function AccountSheet({ open, onClose, onShowShortcuts }) {
  const { user, logout } = useAuth();
  const { counts } = useCounts();
  const titleId = useId();
  return (
    <Dialog open={open} onClose={onClose} className="sheet" labelledBy={titleId}>
      <div className="sheet-grip" aria-hidden="true" />
      <div className="sheet-body">
        <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "4px 12px 12px" }}>
          <span className="avatar" aria-hidden="true">{initial(user?.email)}</span>
          <div style={{ minWidth: 0 }}>
            <h2 id={titleId} className="account-email" style={{ fontSize: 14 }}>{user?.email}</h2>
            <div className="account-role">{user?.role === "admin" ? "Admin" : "Member"}</div>
          </div>
        </div>
        <hr />
        {user?.role === "admin" &&
          ADMIN_ITEMS.map(({ to, label, icon: Icon, countKey }) => (
            <Link key={to} to={to} className="sheet-row" onClick={onClose}>
              <Icon />
              <span style={{ flex: 1 }}>{label}</span>
              {counts[countKey] > 0 && <span className="nav-count" data-attention="true">{counts[countKey]}</span>}
            </Link>
          ))}
        <Link to="/create" state={{ focusComposer: true }} className="sheet-row" onClick={onClose}>
          <IconSparkle />
          <span>Start a new story</span>
        </Link>
        <button type="button" className="sheet-row" style={{ background: "none", border: 0, textAlign: "left" }} onClick={() => { onClose(); onShowShortcuts(); }}>
          <IconDots />
          <span>Keyboard shortcuts</span>
        </button>
        <button type="button" className="sheet-row" style={{ background: "none", border: 0, textAlign: "left", color: "var(--oxide)" }} onClick={() => { onClose(); logout(); }}>
          <IconLogout />
          <span>Sign out</span>
        </button>
        <p className="sidebar-note" style={{ padding: "8px 12px 0" }}>Nothing here posts anywhere by itself.</p>
      </div>
    </Dialog>
  );
}

/**
 * Layout for every signed-in page: navigation chrome, global shortcuts, command menu,
 * focus management and a per-page error boundary.
 */
export default function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { refresh: refreshCounts } = useCounts();
  const [commandOpen, setCommandOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const mainRef = useRef(null);
  const firstRender = useRef(true);
  const goPending = useRef(0);

  const openCommand = useCallback(() => setCommandOpen(true), []);

  // Refresh counts whenever the user moves between pages.
  useEffect(() => {
    refreshCounts();
  }, [location.pathname, refreshCounts]);

  // After client-side navigation, move focus to the new page's heading so screen reader
  // users hear where they landed (and keyboard users start from the top).
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    window.scrollTo({ top: 0 });
    const t = setTimeout(() => {
      // A page that deliberately placed focus (e.g. the Create composer) wins.
      const active = document.activeElement;
      if (active && active !== document.body && mainRef.current?.contains(active) && active !== mainRef.current) return;
      const h = document.getElementById("page-title");
      (h || mainRef.current)?.focus({ preventScroll: true });
    }, 60);
    return () => clearTimeout(t);
  }, [location.pathname]);

  // Global shortcuts: ⌘K / Ctrl+K, "?" and Linear-style "g then key" navigation.
  useEffect(() => {
    const all = [...NAV_ITEMS, ...(user?.role === "admin" ? ADMIN_ITEMS : [])];
    function onKeyDown(e) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCommandOpen((v) => !v);
        return;
      }
      if (e.metaKey || e.ctrlKey || e.altKey || e.repeat || isTypingTarget(e.target) || isModalOpen()) return;
      if (e.key === "?") {
        e.preventDefault();
        setShortcutsOpen(true);
        return;
      }
      const key = e.key.toLowerCase();
      if (key === "g") {
        goPending.current = Date.now();
        return;
      }
      if (goPending.current && Date.now() - goPending.current < 1200) {
        const item = all.find((n) => n.hotkey === key);
        goPending.current = 0;
        if (item) {
          e.preventDefault();
          e.stopImmediatePropagation();
          navigate(item.to);
        }
      }
    }
    // Capture phase so "g r" navigates instead of the Review page treating "r" as Reject.
    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [navigate, user]);

  return (
    <div className="shell">
      <a href="#main" className="skip-link">Skip to content</a>
      <Sidebar onOpenCommand={openCommand} />
      <div style={{ minWidth: 0 }}>
        <TopBar onOpenCommand={openCommand} onOpenAccount={() => setAccountOpen(true)} />
        <main id="main" className="shell-main" ref={mainRef} tabIndex={-1}>
          <div className="shell-content page-enter" key={location.pathname}>
            <ErrorBoundary resetKey={location.pathname}>
              <Outlet />
            </ErrorBoundary>
          </div>
        </main>
      </div>
      <TabBar />
      <CommandMenu open={commandOpen} onClose={() => setCommandOpen(false)} onShowShortcuts={() => setShortcutsOpen(true)} />
      <ShortcutsDialog open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />
      <AccountSheet open={accountOpen} onClose={() => setAccountOpen(false)} onShowShortcuts={() => setShortcutsOpen(true)} />
    </div>
  );
}
