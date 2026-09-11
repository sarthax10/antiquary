import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import * as studioApi from "../api/studio";
import { useCounts } from "../CountsContext";
import { STAGES, stageIndex, useGeneration } from "../GenerationContext";
import { useToast } from "../ToastContext";
import FactCheck from "../components/FactCheck";
import { IconAlert, IconArrowRight, IconCheck, IconChevronL, IconChevronR, IconFlag, IconKeyboard, IconReview, IconSparkle, IconUncertain, IconX } from "../components/icons";
import ShortcutsDialog from "../components/ShortcutsDialog";
import StoryDossier from "../components/StoryDossier";
import { Button, EmptyState, ErrorState, Kbd, Skeleton, Stamp } from "../components/ui";
import VideoFrame from "../components/VideoFrame";
import { claimTotals, formatDuration, pad2, plural } from "../lib/format";
import { prefersReducedMotion, useDocumentTitle, useHotkeys } from "../lib/hooks";

const STAMP_MS = 340;

function QueueItem({ story, index, active, onSelect }) {
  const { flagged, uncertain } = claimTotals(story);
  return (
    <li>
      <button type="button" className="queue-item" aria-current={active ? "true" : undefined} onClick={onSelect}>
        <span className="queue-index meta">{pad2(index + 1)}</span>
        <span className="queue-main">
          <span className="queue-title">{story.title || "Untitled"}</span>
          <span className="queue-meta meta">
            {formatDuration(story.duration_seconds)}
            {flagged > 0 ? (
              <span className="queue-flag" data-tone="oxide"><IconFlag />{flagged}</span>
            ) : uncertain > 0 ? (
              <span className="queue-flag" data-tone="signal"><IconUncertain />{uncertain}</span>
            ) : (
              <span className="queue-flag" data-tone="patina"><IconCheck /></span>
            )}
          </span>
        </span>
      </button>
    </li>
  );
}

function ReviewSkeleton() {
  return (
    <div className="review" aria-busy="true" aria-label="Loading review queue">
      <div className="review-queue" aria-hidden="true">
        {Array.from({ length: 5 }, (_, i) => <Skeleton key={i} height={52} radius={8} style={{ marginBottom: 6 }} />)}
      </div>
      <div className="review-stage"><div className="frame skeleton" /></div>
      <div className="review-dossier" aria-hidden="true">
        <Skeleton width="40%" height={12} />
        <Skeleton width="85%" height={44} style={{ marginTop: 18 }} />
        <Skeleton width="70%" height={20} style={{ marginTop: 18 }} />
        {Array.from({ length: 5 }, (_, i) => <Skeleton key={i} width={`${95 - i * 6}%`} height={12} style={{ marginTop: 12 }} />)}
      </div>
    </div>
  );
}

export default function Review() {
  const [items, setItems] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [index, setIndex] = useState(0);
  const [showVerified, setShowVerified] = useState(false);
  const [leaving, setLeaving] = useState(null); // { id, action }
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [notice, setNotice] = useState(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const videoRef = useRef(null);
  const busy = useRef(false);
  const { refresh: refreshCounts, counts } = useCounts();
  const { status: gen, running } = useGeneration();
  const { toast } = useToast();

  const total = items?.length ?? 0;
  const current = items && total > 0 ? items[Math.min(index, total - 1)] : null;
  useDocumentTitle(total ? `Review (${total})` : "Review");

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const stories = await studioApi.listStories("pending");
      setItems(stories);
      const initial = new URLSearchParams(window.location.search).get("item");
      if (initial && !stories.some((s) => s.id === initial)) setNotice(initial);
    } catch (err) {
      setLoadError(err);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // ?item= wins when it changes from outside (initial load, command menu, a link from
  // another page while Review is open). Applied during render — React's "adjust state
  // when an input changes" pattern — so there's never a frame showing the wrong story.
  const itemParam = searchParams.get("item");
  const [appliedParam, setAppliedParam] = useState(null);
  if (items && itemParam && itemParam !== appliedParam) {
    setAppliedParam(itemParam);
    const found = items.findIndex((s) => s.id === itemParam);
    if (found >= 0 && found !== index) setIndex(found);
  }

  // Otherwise the URL follows the current story, so it's always shareable and reload-safe.
  const currentId = current?.id;
  useEffect(() => {
    if (!currentId || currentId === itemParam) return;
    setAppliedParam(currentId);
    setSearchParams({ item: currentId }, { replace: true, preventScrollReset: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentId]);

  useEffect(() => setShowVerified(false), [current?.id]);

  const select = useCallback((i) => {
    setIndex(i);
    document.querySelector(".review-dossier")?.scrollTo?.({ top: 0 });
  }, []);

  const goNext = useCallback(() => total && select(Math.min(index + 1, total - 1)), [index, total, select]);
  const goPrev = useCallback(() => total && select(Math.max(index - 1, 0)), [index, select, total]);

  const decide = useCallback(
    async (action) => {
      if (!current || busy.current) return;
      busy.current = true;
      const story = current;
      const at = Math.min(index, total - 1);
      videoRef.current?.pause();
      setLeaving({ id: story.id, action });
      try {
        await Promise.all([
          studioApi.decideStory(story.id, action),
          new Promise((r) => setTimeout(r, prefersReducedMotion() ? 0 : STAMP_MS)),
        ]);
        setItems((prev) => prev.filter((s) => s.id !== story.id));
        setIndex((i) => Math.min(i, Math.max(0, total - 2)));
        refreshCounts();
        toast({
          tone: "success",
          title: action === "approve" ? "Approved — moved to Library" : "Rejected — moved to Archive",
          description: story.title || "Untitled",
          action: {
            label: "Undo",
            onClick: async () => {
              try {
                const restored = await studioApi.restoreStory(story.id);
                setItems((prev) => {
                  if (!prev || prev.some((s) => s.id === story.id)) return prev;
                  const next = [...prev];
                  next.splice(Math.min(at, next.length), 0, { ...story, ...restored });
                  return next;
                });
                setIndex(at);
                refreshCounts();
              } catch (err) {
                toast({ tone: "error", title: "Couldn’t undo", description: err.message });
              }
            },
          },
        });
      } catch (err) {
        toast({ tone: "error", title: "Decision not saved", description: err.message || "Try again in a moment." });
      } finally {
        setLeaving(null);
        busy.current = false;
      }
    },
    [current, index, total, refreshCounts, toast]
  );

  useHotkeys(
    {
      a: () => decide("approve"),
      r: () => decide("reject"),
      n: goNext,
      j: goNext,
      ArrowRight: goNext,
      p: goPrev,
      k: goPrev,
      ArrowLeft: goPrev,
      f: () => setShowVerified((v) => !v),
      space: () => {
        const v = videoRef.current;
        if (v) (v.paused ? v.play() : v.pause())?.catch?.(() => {});
      },
    },
    { enabled: !!current }
  );

  const totals = useMemo(() => claimTotals(current), [current]);

  if (loadError) return <ErrorState title="The review queue didn’t load" error={loadError} onRetry={load} />;
  if (items === null) return <ReviewSkeleton />;

  if (total === 0) {
    const idx = running ? stageIndex(gen?.stage) : -1;
    return (
      <div className="review-empty">
        <h1 id="page-title" className="sr-only" tabIndex={-1}>Review</h1>
        <EmptyState
          icon={IconReview}
          title="The desk is clear."
          actions={
            <>
              <Link to="/create" className="btn btn-primary"><IconSparkle />Create a story</Link>
              {counts.approved > 0 && <Link to="/library" className="btn btn-secondary">Open library</Link>}
            </>
          }
        >
          {running
            ? `Nothing to review yet — one story is developing now (${idx >= 0 ? STAGES[idx].label.toLowerCase() : "starting"}). It will appear here the moment it’s rendered.`
            : "Nothing is waiting for your eye. New stories land here as soon as they finish rendering."}
        </EmptyState>
      </div>
    );
  }

  const stamp = leaving?.id === current.id ? leaving.action : null;

  return (
    <div className="review-page">
      <div className="review-bar">
        <div className="review-bar-title">
          <span className="label" style={{ color: "var(--tungsten)" }}>02</span>
          <h1 id="page-title" className="h2" tabIndex={-1}>Review desk</h1>
          <span className="meta review-position" aria-live="polite">
            {pad2(index + 1)} / {pad2(total)}
          </span>
        </div>
        <div className="review-bar-actions">
          <Button variant="ghost" size="sm" icon={IconKeyboard} onClick={() => setShortcutsOpen(true)} className="hide-touch">
            Shortcuts
          </Button>
          <Button variant="secondary" size="sm" icon={IconChevronL} onClick={goPrev} disabled={index === 0} aria-label="Previous story" data-tip="Previous · K" />
          <Button variant="secondary" size="sm" icon={IconChevronR} onClick={goNext} disabled={index >= total - 1} aria-label="Next story" data-tip="Next · J" />
        </div>
      </div>

      {notice && (
        <div className="callout callout-info page-enter" style={{ marginBottom: 20 }} role="status">
          <IconAlert />
          <div>
            <div className="callout-title">That story has already been reviewed</div>
            <span>It’s no longer in the queue. <Link className="link" to={`/stories/${notice}`}>Open it</Link> to see where it went.</span>
          </div>
          <Button size="sm" variant="ghost" icon={IconX} aria-label="Dismiss" onClick={() => setNotice(null)} />
        </div>
      )}

      <div className="review">
        <nav className="review-queue" aria-label="Review queue">
          <div className="review-queue-head">
            <span className="label">Queue</span>
            <span className="meta">{plural(total, "story", "stories")}</span>
          </div>
          <ol>
            {items.map((s, i) => (
              <QueueItem key={s.id} story={s} index={i} active={s.id === current.id} onSelect={() => select(i)} />
            ))}
          </ol>
        </nav>

        <div className="review-stage">
          <VideoFrame ref={videoRef} story={current} stamp={stamp} key={current.id} className={stamp ? "is-leaving" : ""} />
          <div className="review-stage-meta meta">
            <span>9:16</span>
            <span>{formatDuration(current.duration_seconds)}</span>
            <span title="Story ID">#{current.id}</span>
          </div>
        </div>

        <article className="review-dossier" key={current.id} aria-labelledby="story-title">
          <div className="dossier-status">
            <Stamp status="pending" />
          </div>
          <StoryDossier story={current} titleAs="h2" titleId="story-title" />
          <FactCheck story={current} showVerified={showVerified} onToggleVerified={() => setShowVerified((v) => !v)} />

          <div className="decision" role="group" aria-label="Decision">
            {totals.flagged > 0 && (
              <p className="decision-warning">
                <IconFlag /> {plural(totals.flagged, "claim")} {totals.flagged === 1 ? "needs" : "need"} a source — check {totals.flagged === 1 ? "it" : "them"} before approving.
              </p>
            )}
            <div className="decision-buttons">
              <Button variant="secondary" size="lg" icon={IconX} kbd="R" onClick={() => decide("reject")} disabled={!!leaving}>
                Reject
              </Button>
              <Button variant="primary" size="lg" icon={IconCheck} kbd="A" onClick={() => decide("approve")} disabled={!!leaving}>
                Approve
              </Button>
            </div>
            <p className="decision-hint meta hide-touch">
              Decisions save instantly and can be undone. <button type="button" className="link-button" onClick={() => setShortcutsOpen(true)}>All shortcuts <IconArrowRight /></button>
            </p>
          </div>
        </article>
      </div>

      <ShortcutsDialog open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />
    </div>
  );
}
