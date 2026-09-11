import { forwardRef, useState } from "react";
import { videoUrl } from "../api/studio";
import { IconFilm } from "./icons";

/**
 * The review/detail player. Native controls on purpose: they are keyboard- and
 * screen-reader-accessible, support fullscreen/PiP, and never fall out of date.
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
        <video
          ref={ref}
          key={story.id}
          src={videoUrl(story.id)}
          controls
          playsInline
          preload="metadata"
          aria-label={`Video: ${story.title || "Untitled"}`}
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
