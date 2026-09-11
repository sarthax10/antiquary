import { forwardRef, useState } from "react";
import { videoUrl } from "../api/studio";
import { IconFilm } from "./icons";
import VideoPlayer from "./VideoPlayer";

/**
 * The review/detail player. A themed custom player (see VideoPlayer.jsx) rather than
 * the browser's default controls — the ref still resolves to the underlying <video>
 * element itself, so callers that reach into it directly (Review.jsx's Space-to-toggle
 * shortcut) keep working unchanged.
 */
const VideoFrame = forwardRef(function VideoFrame({ story, stamp, className = "" }, ref) {
  const [failed, setFailed] = useState(false);
  return (
    <div className={`frame ${className}`} style={{ viewTransitionName: `story-${story.id}` }}>
      {failed ? (
        <div className="frame-fallback">
          <IconFilm />
          <p>Video unavailable</p>
          <span className="meta">The render for this story couldn’t be loaded.</span>
        </div>
      ) : (
        <VideoPlayer
          ref={ref}
          key={story.id}
          src={videoUrl(story.id)}
          ariaLabel={`Video: ${story.title || "Untitled"}`}
          onError={() => setFailed(true)}
        />
      )}
      {stamp && (
        <div className="frame-stamp" data-action={stamp} aria-hidden="true">
          <span>{stamp === "approve" ? "Approved" : "Rejected"}</span>
        </div>
      )}
    </div>
  );
});

export default VideoFrame;
