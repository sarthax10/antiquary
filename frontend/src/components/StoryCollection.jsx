import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import * as studioApi from "../api/studio";
import { useCounts } from "../CountsContext";
import { useToast } from "../ToastContext";
import { IconRestore, IconSearch, IconX } from "./icons";
import StoryPoster, { PosterSkeleton } from "./StoryPoster";
import { Button, EmptyState, ErrorState, PageHeader } from "./ui";
import { formatDateTime, plural, timeAgo } from "../lib/format";
import { useDocumentTitle, useHotkeys } from "../lib/hooks";

const SORTS = {
  decided_desc: { label: "Recently decided", fn: (a, b) => (b.decided_at || "").localeCompare(a.decided_at || "") },
  decided_asc: { label: "Oldest decisions", fn: (a, b) => (a.decided_at || "").localeCompare(b.decided_at || "") },
  created_desc: { label: "Newest renders", fn: (a, b) => (b.created_at || "").localeCompare(a.created_at || "") },
  title: { label: "Title A–Z", fn: (a, b) => (a.title || "").localeCompare(b.title || "") },
  longest: { label: "Longest first", fn: (a, b) => (b.duration_seconds || 0) - (a.duration_seconds || 0) },
};

/**
 * Library (approved) and Archive (rejected) share one view: searchable, sortable poster
 * grid with a one-click "return to review" that can itself be undone.
 */
export default function StoryCollection({ status, index, title, description, empty }) {
  useDocumentTitle(title);
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("decided_desc");
  const [restoring, setRestoring] = useState(null);
  const searchRef = useRef(null);
  const { refresh: refreshCounts, counts } = useCounts();
  const { toast } = useToast();

  const load = useCallback(() => {
    setError(null);
    studioApi.listStories(status).then(setItems).catch(setError);
  }, [status]);

  useEffect(load, [load]);

  useHotkeys({ "/": () => searchRef.current?.focus() });

  const visible = useMemo(() => {
    if (!items) return [];
    const q = query.trim().toLowerCase();
    const filtered = q
      ? items.filter((s) => `${s.title} ${s.hook} ${s.topic} ${s.narration}`.toLowerCase().includes(q))
      : items;
    return [...filtered].sort(SORTS[sort].fn);
  }, [items, query, sort]);

  async function restore(story) {
    setRestoring(story.id);
    try {
      await studioApi.restoreStory(story.id);
      setItems((prev) => prev.filter((s) => s.id !== story.id));
      refreshCounts();
      const action = status === "approved" ? "approve" : "reject";
      toast({
        tone: "success",
        title: "Moved back to the review desk",
        description: story.title || "Untitled",
        action: {
          label: "Undo",
          onClick: async () => {
            try {
              await studioApi.decideStory(story.id, action);
              load();
              refreshCounts();
            } catch (err) {
              toast({ tone: "error", title: "Couldn’t undo", description: err.message });
            }
          },
        },
      });
    } catch (err) {
      toast({ tone: "error", title: "Couldn’t move it back", description: err.message });
    } finally {
      setRestoring(null);
    }
  }

  const verb = status === "approved" ? "Approved" : "Rejected";

  return (
    <>
      <PageHeader
        index={index}
        eyebrow={status === "approved" ? "Approved stories" : "Rejected stories"}
        title={title}
        description={description}
      />

      {error ? (
        <ErrorState title={`${title} didn’t load`} error={error} onRetry={load} />
      ) : items === null ? (
        <div className="poster-grid poster-grid-lg" aria-busy="true" aria-label={`Loading ${title}`}>
          {Array.from({ length: 8 }, (_, i) => <PosterSkeleton key={i} />)}
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={empty.icon}
          title={empty.title}
          actions={
            counts.pending > 0 ? (
              <Link to="/review" className="btn btn-primary">Open review desk · {counts.pending} waiting</Link>
            ) : (
              <Link to="/create" className="btn btn-secondary">Create a story</Link>
            )
          }
        >
          {empty.body}
        </EmptyState>
      ) : (
        <>
          <div className="toolbar" role="search">
            <div className="input-wrap has-icon toolbar-search">
              <IconSearch className="input-icon" />
              <label htmlFor={`search-${status}`} className="sr-only">Search {title}</label>
              <input
                ref={searchRef}
                id={`search-${status}`}
                className="input input-sm"
                type="search"
                placeholder="Search titles, hooks, prompts…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Escape" && (setQuery(""), e.currentTarget.blur())}
              />
              {!query && <kbd className="kbd toolbar-kbd" aria-hidden="true">/</kbd>}
            </div>
            <label className="toolbar-sort">
              <span className="sr-only">Sort by</span>
              <select className="select" value={sort} onChange={(e) => setSort(e.target.value)}>
                {Object.entries(SORTS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </select>
            </label>
            <span className="meta toolbar-count" aria-live="polite">
              {query ? `${visible.length} of ${items.length}` : plural(items.length, "story", "stories")}
            </span>
          </div>

          {visible.length === 0 ? (
            <EmptyState icon={IconSearch} title="No stories match." actions={<Button onClick={() => setQuery("")} icon={IconX}>Clear search</Button>}>
              Nothing in {title.toLowerCase()} mentions “{query}”.
            </EmptyState>
          ) : (
            <ul className="poster-grid poster-grid-lg stagger">
              {visible.map((s, i) => (
                <li key={s.id} style={{ "--i": i }} className="collection-item">
                  <StoryPoster
                    story={s}
                    to={`/stories/${s.id}`}
                    showStatus={false}
                    meta={<span title={formatDateTime(s.decided_at)}>{verb} {timeAgo(s.decided_at)}</span>}
                  />
                  <Button size="sm" variant="ghost" icon={IconRestore} className="collection-restore" loading={restoring === s.id} onClick={() => restore(s)}>
                    Return to review
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </>
  );
}
