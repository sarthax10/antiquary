import { useEffect, useRef, useState } from "react";
import { videoUrl } from "../api/studio";
import { claimTotals, formatDuration } from "../lib/format";
import { prefersReducedMotion, useInView } from "../lib/hooks";
import { TransitionLink } from "../lib/transitions";
import { IconFilm, IconFlag } from "./icons";
import { Stamp } from "./ui";

const canHover = () => typeof window !== "undefined" && window.matchMedia?.("(hover: hover) and (pointer: fine)").matches;

/**
 * A story as a 9:16 poster. The first frame is the poster image (media fragment #t=0.1),
 * the video only starts loading when the card nears the viewport, and on devices with a
 * real pointer a short hover plays a muted preview.
 */
export default function StoryPoster({ story, to, showStatus = true, meta, style, className = "" }) {
  const [ref, inView] = useInView("300px");
  const videoRef = useRef(null);
  const hoverTimer = useRef(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [progress, setProgress] = useState(0);
  const { flagged } = claimTotals(story);

  const metaTimer = useRef(null);
  useEffect(() => () => {
    clearTimeout(hoverTimer.current);
    clearTimeout(metaTimer.current);
  }, []);

  function startPreview() {
    if (!ready || failed || !canHover() || prefersReducedMotion()) return;
    hoverTimer.current = setTimeout(() => {
      const v = videoRef.current;
      if (!v) return;
      v.currentTime = 0;
      v.play().then(() => setPreviewing(true)).catch(() => {});
    }, 380);
  }

  function stopPreview() {
    clearTimeout(hoverTimer.current);
    const v = videoRef.current;
    if (v && previewing) {
      v.pause();
      v.currentTime = 0.1;
    }
    setPreviewing(false);
    setProgress(0);
  }

  return (
    <TransitionLink
      to={to}
      className={`poster ${className}`}
      style={style}
      onMouseEnter={startPreview}
      onMouseLeave={stopPreview}
      aria-label={`${story.title || "Untitled"}, ${formatDuration(story.duration_seconds)}${showStatus ? `, ${story.status}` : ""}`}
    >
      <div className="poster-frame" ref={ref} style={{ viewTransitionName: `story-${story.id}` }}>
        {!ready && !failed && <span className="skeleton poster-skeleton" aria-hidden="true" />}
        {failed ? (
          <div className="poster-fallback" aria-hidden="true">
            <IconFilm />
            <span>No video</span>
          </div>
        ) : (
          inView && (
            <video
              ref={videoRef}
              src={`${videoUrl(story.id)}#t=0.1`}
              muted
              playsInline
              preload="metadata"
              tabIndex={-1}
              aria-hidden="true"
              data-ready={ready ? "true" : undefined}
              onLoadedData={() => setReady(true)}
              // iOS Safari loads metadata but withholds frame data until the user
              // interacts — stop the skeleton shimmer anyway rather than pulse forever.
              onLoadedMetadata={() => { metaTimer.current = setTimeout(() => setReady(true), 1500); }}
              onError={() => setFailed(true)}
              onTimeUpdate={(e) => previewing && setProgress(e.currentTarget.currentTime / (e.currentTarget.duration || 1))}
              onEnded={stopPreview}
            />
          )
        )}
        <span className="poster-shade" aria-hidden="true" />
        <span className="poster-top" aria-hidden="true">
          {showStatus ? <Stamp status={story.status} className="stamp-overlay">{story.status}</Stamp> : <span />}
          <span className="poster-duration">{formatDuration(story.duration_seconds)}</span>
        </span>
        {flagged > 0 && (
          <span className="poster-flag" aria-hidden="true">
            <IconFlag /> {flagged}
          </span>
        )}
        <span className="poster-progress" style={{ transform: `scaleX(${progress})` }} aria-hidden="true" />
      </div>
      <div className="poster-body">
        <span className="poster-title">{story.title || "Untitled"}</span>
        {meta && <span className="meta poster-meta">{meta}</span>}
      </div>
    </TransitionLink>
  );
}

export function PosterSkeleton() {
  return (
    <div className="poster" aria-hidden="true">
      <div className="poster-frame"><span className="skeleton poster-skeleton" /></div>
      <div className="poster-body">
        <span className="skeleton skeleton-text" style={{ width: "80%" }} />
        <span className="skeleton skeleton-text" style={{ width: "40%", marginTop: 6 }} />
      </div>
    </div>
  );
}
