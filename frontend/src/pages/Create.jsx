import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import * as studioApi from "../api/studio";
import { useCounts } from "../CountsContext";
import { IconCreate, IconStop } from "../components/icons";

// Kept in sync with app/generation/job_manager.py's STAGES — real pipeline steps, not a
// simulated timer.
const STAGES = [
  ["writing", "Writing the story"],
  ["fact_checking", "Fact-checking claims"],
  ["sourcing_visuals", "Sourcing visuals"],
  ["recording_narration", "Recording narration"],
  ["generating_captions", "Generating captions"],
  ["rendering", "Rendering the film"],
];
const STAGE_KEYS = STAGES.map(([k]) => k);

function StageList({ currentStageKey }) {
  const currentIdx = STAGE_KEYS.indexOf(currentStageKey);
  return (
    <div className="stage-list">
      {STAGES.map(([key, label], i) => {
        const cls = i < currentIdx ? "done" : i === currentIdx ? "active" : "pending";
        return (
          <div key={key} className={`stage-row ${cls}`}>
            <span className="stage-num">{i < currentIdx ? "✓" : i === currentIdx ? "●" : "○"}</span>
            <span className="label">{label}</span>
          </div>
        );
      })}
    </div>
  );
}

function Elapsed({ startedAt }) {
  const [text, setText] = useState("0:00");
  useEffect(() => {
    const tick = () => {
      const s = Math.max(0, Math.floor(Date.now() / 1000 - startedAt));
      setText(`${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [startedAt]);
  return <span>{text}</span>;
}

export default function Create() {
  const [status, setStatus] = useState(null);
  const [topic, setTopic] = useState("");
  const [recent, setRecent] = useState([]);
  const pollRef = useRef(null);
  const { refresh: refreshCounts } = useCounts();

  function loadRecent() {
    studioApi.recentStories(8).then(setRecent);
  }

  function loadStatus() {
    studioApi.generationStatus().then(setStatus);
  }

  useEffect(() => {
    loadStatus();
    loadRecent();
  }, []);

  useEffect(() => {
    if (status?.status !== "running") {
      clearInterval(pollRef.current);
      return;
    }
    const lastStage = status.stage;
    pollRef.current = setInterval(async () => {
      const next = await studioApi.generationStatus();
      if (next.status !== "running" || next.stage !== lastStage) {
        clearInterval(pollRef.current);
        setStatus(next);
        if (next.status !== "running") {
          loadRecent();
          refreshCounts();
        }
      }
    }, 2500);
    return () => clearInterval(pollRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  async function handleGenerate(e) {
    e.preventDefault();
    await studioApi.startGeneration(topic);
    setTopic("");
    loadStatus();
  }

  async function handleCancel() {
    await studioApi.cancelGeneration();
    loadStatus();
  }

  if (!status) return null;

  return (
    <>
      {status.status === "running" ? (
        <div className="progress-panel">
          <div className="progress-head"><h2>Creating your story</h2></div>
          <p className="progress-topic">&ldquo;{status.topic || "a free pick — let the archive decide"}&rdquo;</p>
          <StageList currentStageKey={status.stage} />
          <div className="progress-foot">
            <span className="elapsed"><Elapsed startedAt={status.started_at} /> elapsed &middot; usually a few minutes</span>
            <button type="button" className="btn btn-danger-outline" onClick={handleCancel}><IconStop />Stop</button>
          </div>
        </div>
      ) : (
        <>
          {status.status === "error" && (
            <div className="banner banner-error">
              <strong>The last generation failed.</strong><br />
              <span style={{ color: "var(--ink-muted)" }}>{(status.error || "Unknown error").slice(-400)}</span>
            </div>
          )}
          {status.status === "cancelled" && (
            <div className="banner banner-info">Last generation was stopped.</div>
          )}
          <div className="create-panel">
            <h2>What should history uncover?</h2>
            <p className="prompt-hint">Give it a direction, or leave it blank and let the archive surprise you.</p>
            <form onSubmit={handleGenerate}>
              <textarea
                className="topic-input"
                placeholder="The strangest rituals of Ancient Rome…"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                autoFocus
              />
              <div className="create-row">
                <div className="create-facts">
                  <span>Historical short<span className="dot" />~30&ndash;45s</span>
                  <span>9:16 vertical</span>
                  <span>Fact-checked</span>
                </div>
                <button type="submit" className="btn btn-gold"><IconCreate />Generate story</button>
              </div>
            </form>
            <p className="advanced-note">Advanced settings (voice, pacing, visual style) — coming soon.</p>
          </div>
        </>
      )}

      {recent.length > 0 && (
        <>
          <div className="recent-head"><h3>Recent stories</h3></div>
          <div className="recent-grid">
            {recent.map((s) => (
              <Link
                key={s.id}
                className="recent-card"
                to={s.status === "pending" ? `/review?item=${s.id}` : s.status === "approved" ? "/library" : "/archive"}
              >
                <video muted preload="metadata" src={studioApi.videoUrl(s.id)} />
                <div className={`status-tag ${s.status}`}>{s.status}</div>
                <div className="r-title">{s.title || "Untitled"}</div>
                <div className="r-meta">{formatDuration(s.duration_seconds)}</div>
              </Link>
            ))}
          </div>
        </>
      )}
    </>
  );
}

function formatDuration(seconds) {
  if (seconds == null) return "—";
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
