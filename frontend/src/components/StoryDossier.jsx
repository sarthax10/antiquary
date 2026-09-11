import { formatDuration, timeAgo, formatDateTime, wordCount } from "../lib/format";

/** Title, hook and narration — the editorial half of a story. */
export default function StoryDossier({ story, titleAs: Title = "h1", titleId }) {
  const words = wordCount(story.narration);
  return (
    <div className="dossier-text">
      <div className="dossier-kicker meta">
        <span title={formatDateTime(story.created_at)}>Rendered {timeAgo(story.created_at)}</span>
        <span aria-hidden="true">·</span>
        <span>{formatDuration(story.duration_seconds)}</span>
        <span aria-hidden="true">·</span>
        <span>{story.topic ? <>Prompt “{story.topic}”</> : "Free pick"}</span>
      </div>
      <Title className="dossier-title" id={titleId} tabIndex={titleId ? -1 : undefined}>{story.title || "Untitled"}</Title>
      {story.hook && (
        <blockquote className="dossier-hook">
          <p>{story.hook}</p>
        </blockquote>
      )}
      {story.narration && (
        <div className="dossier-narration">
          <div className="dossier-section-head">
            <h2 className="label">Narration</h2>
            <span className="meta">{words} words</span>
          </div>
          <p>{story.narration}</p>
        </div>
      )}
    </div>
  );
}
