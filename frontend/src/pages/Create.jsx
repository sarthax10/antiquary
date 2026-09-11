import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import * as studioApi from "../api/studio";
import { STAGES, stageIndex, useGeneration } from "../GenerationContext";
import { useToast } from "../ToastContext";
import { StageSegments } from "../components/GenerationIndicator";
import { IconAlert, IconArrowRight, IconCheck, IconInfo, IconShuffle, IconSparkle, IconStop, IconX } from "../components/icons";
import StoryPoster, { PosterSkeleton } from "../components/StoryPoster";
import StoryPreviewModal from "../components/StoryPreviewModal";
import { Button, Callout, ConfirmDialog, ErrorState, Kbd } from "../components/ui";
import { formatDateTime, pad2, timeAgo } from "../lib/format";
import { modKey, safeStorage, useDocumentTitle, useNow } from "../lib/hooks";
import { requestNotificationPermission } from "../lib/notify";

// The backend stores topics in a String(500) column.
const MAX_TOPIC = 500;

// Starting points, not settings: clicking one only fills the prompt box with text the
// user can edit. They exist to show new members what a good, narrow prompt looks like.
const SUGGESTIONS = [
  "A shipwreck nobody could explain",
  "The strangest rituals of Ancient Rome",
  "An inventor history forgot",
  "A hoax that fooled an entire nation",
  "A tiny decision that changed a war",
];

function useDismissed(key) {
  const [dismissed, setDismissed] = useState(() => (key ? safeStorage.get(`antiquary:dismissed:${key}`) === "1" : false));
  useEffect(() => {
    setDismissed(key ? safeStorage.get(`antiquary:dismissed:${key}`) === "1" : false);
  }, [key]);
  const dismiss = useCallback(() => {
    if (key) safeStorage.set(`antiquary:dismissed:${key}`, "1");
    setDismissed(true);
  }, [key]);
  return [dismissed, dismiss];
}

function Composer({ onStarted }) {
  const { start } = useGeneration();
  const { toast } = useToast();
  const location = useLocation();
  const [topic, setTopic] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const ref = useRef(null);
  const trimmed = topic.trim();
  const remaining = MAX_TOPIC - topic.length;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    // Only steal focus on a pointer-less landing or when explicitly asked to (command
    // menu / "new story"), so screen reader users aren't dropped past the page heading.
    if (location.state?.focusComposer || window.matchMedia?.("(hover: hover)").matches) {
      el.focus({ preventScroll: true });
    }
  }, [location.state]);

  // Auto-grow the textarea with its content.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 320)}px`;
  }, [topic]);

  async function submit(e) {
    e?.preventDefault();
    if (submitting) return;
    // Asked for here, not on page load: a real click is what most browsers require
    // before they'll show the permission prompt at all, and it's the one moment where
    // "notify me when this finishes" is obviously relevant rather than a cold-open ask.
    requestNotificationPermission();
    setSubmitting(true);
    try {
      const res = await start(trimmed);
      if (res?.started === false) {
        toast({ tone: "error", title: "Couldn’t start a new story", description: res.message || "A generation is already running." });
      } else {
        setTopic("");
        onStarted?.();
      }
    } catch (err) {
      toast({ tone: "error", title: "Couldn’t start a new story", description: err.message });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="composer panel" onSubmit={submit} aria-labelledby="page-title">
      <label htmlFor="topic" className="sr-only">Story prompt (optional)</label>
      <textarea
        id="topic"
        ref={ref}
        className="composer-input"
        placeholder="A moment, a person, a place… or leave it blank."
        value={topic}
        maxLength={MAX_TOPIC}
        rows={2}
        onChange={(e) => setTopic(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit(e);
        }}
        aria-describedby="topic-help"
      />

      <div className="composer-suggestions" role="group" aria-label="Prompt ideas">
        <span className="label">Try</span>
        {SUGGESTIONS.map((s) => (
          <button key={s} type="button" className="chip" aria-pressed={topic === s} onClick={() => { setTopic(s); ref.current?.focus(); }}>
            {s}
          </button>
        ))}
      </div>

      <div className="composer-foot">
        <p id="topic-help" className="composer-specs meta">
          <span>≈ 30–45 s</span>
          <span>9:16 vertical</span>
          <span>Fact-checked</span>
          {remaining <= 80 && <span style={{ color: remaining <= 20 ? "var(--oxide)" : "var(--tungsten)" }}>{remaining} characters left</span>}
        </p>
        <div className="composer-submit">
          <span className="composer-kbd" aria-hidden="true"><Kbd>{modKey}</Kbd><Kbd>↵</Kbd></span>
          <Button type="submit" variant="primary" size="lg" icon={trimmed ? IconSparkle : IconShuffle} loading={submitting}>
            {trimmed ? "Generate story" : "Surprise me"}
          </Button>
        </div>
      </div>
      <p className="composer-note">
        <IconInfo /> Voice, pacing and visual style controls are coming soon — for now every story uses the studio defaults.
      </p>
    </form>
  );
}

function Developing() {
  const { status, cancel } = useGeneration();
  const { toast } = useToast();
  const [confirming, setConfirming] = useState(false);
  const [stopping, setStopping] = useState(false);
  const now = useNow(1000, true);
  const idx = stageIndex(status.stage);
  const elapsed = Math.max(0, Math.floor(now / 1000 - (status.started_at || now / 1000)));

  async function stop() {
    setStopping(true);
    try {
      const res = await cancel();
      if (res?.cancelled === false) toast({ tone: "error", title: "Nothing to stop", description: res.message });
      else toast({ title: "Generation stopped" });
    } catch (err) {
      toast({ tone: "error", title: "Couldn’t stop the generation", description: err.message });
    } finally {
      setStopping(false);
      setConfirming(false);
    }
  }

  return (
    <section className="developing panel" aria-labelledby="developing-title" aria-live="polite">
      <div className="developing-head">
        <span className="developing-live">
          <span className="live-dot" aria-hidden="true" />
          <span className="label" style={{ color: "var(--tungsten)" }}>Developing</span>
        </span>
        <span className="meta tabular" aria-label={`Elapsed ${Math.floor(elapsed / 60)} minutes ${elapsed % 60} seconds`}>
          {pad2(Math.floor(elapsed / 60))}:{pad2(elapsed % 60)} elapsed
        </span>
      </div>

      <h2 id="developing-title" className="developing-topic">
        {status.topic ? <>“{status.topic}”</> : <span className="italic muted">A free pick — the archive decides.</span>}
      </h2>

      <StageSegments stage={status.stage} />

      <ol className="stages">
        {STAGES.map((s, i) => {
          const state = i < idx ? "done" : i === idx ? "active" : "pending";
          return (
            <li key={s.key} className="stage" data-state={state} aria-current={state === "active" ? "step" : undefined}>
              <span className="stage-num meta">{state === "done" ? <IconCheck /> : pad2(i + 1)}</span>
              <span className="stage-text">
                <span className="stage-label">{s.label}</span>
                {state === "active" && <span className="stage-detail">{s.detail}</span>}
              </span>
              <span className="stage-state meta">{state === "done" ? "Done" : state === "active" ? "In progress" : ""}</span>
            </li>
          );
        })}
      </ol>

      <div className="developing-foot">
        <p className="muted" style={{ fontSize: "var(--text-sm)" }}>
          Stages update as the pipeline actually reaches them. Usually a few minutes — you can leave this page.
        </p>
        <Button variant="danger" icon={IconStop} onClick={() => setConfirming(true)}>Stop</Button>
      </div>

      <ConfirmDialog
        open={confirming}
        title="Stop this generation?"
        confirmLabel="Stop generation"
        tone="danger"
        busy={stopping}
        onConfirm={stop}
        onCancel={() => setConfirming(false)}
      >
        The work done so far is discarded and no story is created. You can start a new one right away.
      </ConfirmDialog>
    </section>
  );
}

function LastRunNotice({ status, recent }) {
  const key = status?.finished_at ? `${status.status}-${status.finished_at}` : null;
  const [dismissed, dismiss] = useDismissed(key);
  if (!status || dismissed || !status.finished_at) return null;
  const ageMin = (Date.now() / 1000 - status.finished_at) / 60;

  if (status.status === "error") {
    return (
      <Callout
        tone="error"
        icon={IconAlert}
        title="The last generation failed"
        role="alert"
        actions={<Button size="sm" variant="ghost" icon={IconX} aria-label="Dismiss" onClick={dismiss} />}
      >
        <span>Finished {timeAgo(status.finished_at * 1000)}{status.topic ? <> · “{status.topic}”</> : null}. Nothing was saved — try again, or try a different prompt.</span>
        {status.error && (
          <details>
            <summary>Technical details</summary>
            <pre>{status.error.slice(-800)}</pre>
          </details>
        )}
      </Callout>
    );
  }
  if (status.status === "cancelled" && ageMin < 24 * 60) {
    return (
      <Callout tone="info" icon={IconInfo} title="The last generation was stopped" actions={<Button size="sm" variant="ghost" icon={IconX} aria-label="Dismiss" onClick={dismiss} />}>
        <span>Stopped {timeAgo(status.finished_at * 1000)}. No story was created.</span>
      </Callout>
    );
  }
  if (status.status === "done" && status.story_id && ageMin < 60) {
    const story = recent?.find((s) => s.id === status.story_id);
    if (!story || story.status !== "pending") return null;
    return (
      <Callout
        tone="success"
        icon={IconCheck}
        title="Your latest story is ready"
        actions={
          <>
            <Link to={`/review?item=${story.id}`} className="btn btn-sm btn-primary">Review now<IconArrowRight /></Link>
            <Button size="sm" variant="ghost" icon={IconX} aria-label="Dismiss" onClick={dismiss} />
          </>
        }
      >
        <span>“{story.title || "Untitled"}” finished {timeAgo(status.finished_at * 1000)} and is waiting on the review desk.</span>
      </Callout>
    );
  }
  return null;
}

export default function Create() {
  useDocumentTitle("Create");
  const { status, running, onFinish, error: statusError, refresh: refreshStatus } = useGeneration();
  const [recent, setRecent] = useState(null);
  const [recentError, setRecentError] = useState(null);
  const [previewStory, setPreviewStory] = useState(null);

  const handlePreviewChange = useCallback((updated) => {
    setPreviewStory((s) => (s ? { ...s, ...updated } : s));
    setRecent((r) => r?.map((s) => (s.id === updated.id ? { ...s, ...updated } : s)) ?? r);
  }, []);

  const loadRecent = useCallback(() => {
    studioApi
      .recentStories(12)
      .then((r) => {
        setRecent(r);
        setRecentError(null);
      })
      .catch(setRecentError);
  }, []);

  useEffect(loadRecent, [loadRecent]);
  useEffect(() => onFinish(loadRecent), [onFinish, loadRecent]);

  const pendingRecent = useMemo(() => (recent || []).filter((s) => s.status === "pending").length, [recent]);

  return (
    <div className="create">
      <section className="create-hero" aria-labelledby="page-title">
        <div className="page-eyebrow">
          <span className="label" style={{ color: "var(--tungsten)" }}>01</span>
          <span className="rule" aria-hidden="true" />
          <span className="label">Create</span>
        </div>
        <h1 id="page-title" className="display create-title" tabIndex={-1}>
          What should history <em>uncover?</em>
        </h1>
        <p className="lead create-lead">
          Describe a moment, a person or a place — or leave it blank and let the archive choose. Each story is written, fact-checked, narrated and cut to a vertical short.
        </p>
      </section>

      <div className="create-stack">
        {status === null && statusError ? (
          <ErrorState title="Couldn’t check the generation status" error={statusError} onRetry={refreshStatus} />
        ) : status === null ? (
          <div className="panel skeleton" style={{ height: 260 }} aria-hidden="true" />
        ) : running ? (
          <Developing />
        ) : (
          <>
            <LastRunNotice status={status} recent={recent} />
            <Composer />
          </>
        )}
      </div>

      <section className="recent" aria-labelledby="recent-title">
        <div className="section-head">
          <div>
            <h2 id="recent-title" className="h2">Recently developed</h2>
            <p className="muted" style={{ fontSize: "var(--text-sm)", marginTop: 4 }}>
              The latest stories from every member of the studio.
            </p>
          </div>
          {pendingRecent > 0 && (
            <Link to="/review" className="btn btn-sm btn-secondary">
              Open review desk <IconArrowRight />
            </Link>
          )}
        </div>

        {recentError ? (
          <Callout tone="error" title="Recent stories didn’t load" actions={<Button size="sm" onClick={loadRecent}>Try again</Button>}>
            <span>{recentError.message}</span>
          </Callout>
        ) : recent === null ? (
          <div className="poster-grid" aria-busy="true" aria-label="Loading recent stories">
            {Array.from({ length: 6 }, (_, i) => <PosterSkeleton key={i} />)}
          </div>
        ) : recent.length === 0 ? (
          <p className="recent-empty muted">
            Nothing has been developed yet. Your first story will appear here the moment it finishes rendering.
          </p>
        ) : (
          <ul className="poster-grid stagger">
            {recent.map((s, i) => (
              <li key={s.id} style={{ "--i": i }}>
                <StoryPoster
                  story={s}
                  to={s.status === "pending" ? `/review?item=${s.id}` : `/stories/${s.id}`}
                  onClick={(e) => { e.preventDefault(); setPreviewStory(s); }}
                  meta={<span title={formatDateTime(s.created_at)}>{timeAgo(s.created_at)}</span>}
                />
              </li>
            ))}
          </ul>
        )}
      </section>

      <StoryPreviewModal story={previewStory} onClose={() => setPreviewStory(null)} onChange={handlePreviewChange} />
    </div>
  );
}
