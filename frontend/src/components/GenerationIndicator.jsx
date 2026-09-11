import { Link } from "react-router-dom";
import { STAGES, stageIndex, useGeneration } from "../GenerationContext";

/** Segmented bar of the six real pipeline stages. */
export function StageSegments({ stage, label }) {
  const idx = stageIndex(stage);
  return (
    <div
      className="segments"
      style={{ "--n": STAGES.length }}
      role="progressbar"
      aria-label={label || "Generation progress"}
      aria-valuemin={0}
      aria-valuemax={STAGES.length}
      aria-valuenow={Math.max(0, idx)}
      aria-valuetext={idx >= 0 ? `Stage ${idx + 1} of ${STAGES.length}: ${STAGES[idx].label}` : "Starting"}
    >
      {STAGES.map((s, i) => (
        <span key={s.key} data-state={i < idx ? "done" : i === idx ? "active" : "pending"} />
      ))}
    </div>
  );
}

/** Sidebar widget: visible on every page while a render is in progress. */
export function GenerationWidget() {
  const { status, running } = useGeneration();
  if (!running) return null;
  const idx = stageIndex(status.stage);
  return (
    <Link to="/create" className="gen-widget" aria-label={`Generation in progress: ${idx >= 0 ? STAGES[idx].label : "starting"}. Open Create.`}>
      <span className="gen-widget-head">
        <span className="live-dot" aria-hidden="true" />
        Developing
        <span className="meta">{idx >= 0 ? `${idx + 1}/${STAGES.length}` : "—"}</span>
      </span>
      <StageSegments stage={status.stage} />
      <span className="gen-widget-stage">{idx >= 0 ? STAGES[idx].label : "Starting up…"}</span>
    </Link>
  );
}

/** Compact pill for the mobile top bar. */
export function GenerationPill() {
  const { status, running } = useGeneration();
  if (!running) return null;
  const idx = stageIndex(status.stage);
  return (
    <Link to="/create" className="topbar-gen" aria-label={`Generation in progress, stage ${idx + 1} of ${STAGES.length}`}>
      <span className="live-dot" aria-hidden="true" />
      {idx >= 0 ? `${idx + 1}/${STAGES.length}` : "…"}
    </Link>
  );
}
