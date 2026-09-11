import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../AuthContext";
import { useCounts } from "../CountsContext";
import { Dialog, Kbd } from "./ui";
import { IconFilm, IconKeyboard, IconLogout, IconSearch, IconSparkle } from "./icons";
import { ADMIN_ITEMS, NAV_ITEMS } from "./nav";

const STATUS_WORD = { pending: "In review", approved: "Library", rejected: "Archive" };

function score(text, q) {
  const t = text.toLowerCase();
  if (!q) return 1;
  if (t.startsWith(q)) return 3;
  if (t.split(/\s+/).some((w) => w.startsWith(q))) return 2;
  return t.includes(q) ? 1 : 0;
}

/** ⌘K / Ctrl+K: jump anywhere, run an action, or find any story by title. */
export default function CommandMenu({ open, onClose, onShowShortcuts }) {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { lists } = useCounts();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);
  const listRef = useRef(null);
  const listId = useId();
  const titleId = useId();

  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
    }
  }, [open]);

  const items = useMemo(() => {
    const q = query.trim().toLowerCase();
    const nav = [...NAV_ITEMS, ...(user?.role === "admin" ? ADMIN_ITEMS : [])].map((n) => ({
      id: `nav-${n.to}`,
      group: "Go to",
      title: n.label,
      icon: n.icon,
      hint: `G ${n.hotkey.toUpperCase()}`,
      run: () => navigate(n.to),
    }));
    const actions = [
      { id: "new", group: "Actions", title: "Start a new story", icon: IconSparkle, run: () => navigate("/create", { state: { focusComposer: true } }) },
      { id: "shortcuts", group: "Actions", title: "Keyboard shortcuts", icon: IconKeyboard, hint: "?", run: () => onShowShortcuts?.() },
      { id: "logout", group: "Actions", title: "Sign out", icon: IconLogout, run: () => logout() },
    ];
    const stories = [...lists.pending, ...lists.approved, ...lists.rejected].map((s) => ({
      id: `story-${s.id}`,
      group: "Stories",
      title: s.title || "Untitled",
      sub: STATUS_WORD[s.status],
      icon: IconFilm,
      keywords: `${s.topic || ""} ${s.hook || ""}`,
      run: () => navigate(s.status === "pending" ? `/review?item=${s.id}` : `/stories/${s.id}`),
    }));

    const ranked = [...nav, ...actions]
      .map((it) => ({ it, s: score(it.title, q) }))
      .filter((x) => x.s > 0)
      .map((x) => x.it);
    const storyHits = q
      ? stories
          .map((it) => ({ it, s: Math.max(score(it.title, q) * 2, score(it.keywords, q)) }))
          .filter((x) => x.s > 0)
          .sort((a, b) => b.s - a.s)
          .slice(0, 8)
          .map((x) => x.it)
      : stories.slice(0, 5);
    return [...ranked, ...storyHits];
  }, [query, lists, user, navigate, logout, onShowShortcuts]);

  useEffect(() => {
    if (active >= items.length) setActive(Math.max(0, items.length - 1));
  }, [items.length, active]);

  useEffect(() => {
    listRef.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
  }, [active]);

  function run(item) {
    onClose();
    // Let the dialog close (and return focus) before navigating.
    requestAnimationFrame(() => item.run());
  }

  function onKeyDown(e) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => (items.length ? (i + 1) % items.length : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => (items.length ? (i - 1 + items.length) % items.length : 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (items[active]) run(items[active]);
    }
  }

  let lastGroup = null;
  return (
    <Dialog open={open} onClose={onClose} className="command" labelledBy={titleId} initialFocusRef={inputRef}>
      <h2 id={titleId} className="sr-only">Command menu</h2>
      <div className="command-input-row">
        <IconSearch />
        <input
          ref={inputRef}
          className="command-input"
          placeholder="Search stories, pages and actions…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActive(0);
          }}
          onKeyDown={onKeyDown}
          role="combobox"
          aria-expanded="true"
          aria-controls={listId}
          aria-activedescendant={items[active] ? `${listId}-${items[active].id}` : undefined}
          aria-autocomplete="list"
          autoComplete="off"
          spellCheck="false"
        />
        <Kbd>Esc</Kbd>
      </div>
      <div className="command-list" id={listId} role="listbox" ref={listRef} aria-label="Results">
        {items.length === 0 && <div className="command-empty">Nothing matches “{query}”.</div>}
        {items.map((item, i) => {
          const header = item.group !== lastGroup ? item.group : null;
          lastGroup = item.group;
          const Icon = item.icon;
          return (
            <div key={item.id} role="presentation">
              {header && <div className="label command-group-label" role="presentation">{header}</div>}
              <div
                id={`${listId}-${item.id}`}
                role="option"
                aria-selected={i === active}
                className="command-item"
                onMouseMove={() => i !== active && setActive(i)}
                onClick={() => run(item)}
              >
                <Icon />
                <span className="command-item-title">{item.title}</span>
                {item.sub && <span className="meta">{item.sub}</span>}
                {item.hint && <span className="shortcut-keys">{item.hint.split(" ").map((k) => <Kbd key={k}>{k}</Kbd>)}</span>}
              </div>
            </div>
          );
        })}
      </div>
      <div className="command-foot" aria-hidden="true">
        <span><Kbd>↑</Kbd><Kbd>↓</Kbd> move</span>
        <span><Kbd>↵</Kbd> open</span>
        <span><Kbd>Esc</Kbd> close</span>
      </div>
    </Dialog>
  );
}
