import { useEffect, useState } from "react";
import * as socialApi from "../api/social";
import * as studioApi from "../api/studio";
import { useCounts } from "../CountsContext";
import { IconRestore } from "./icons";
import PublishControls from "./PublishControls";

function formatDuration(seconds) {
  if (seconds == null) return "—";
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export default function DecidedList({ status, emptyTitle, emptySub, showPublish = false }) {
  const [items, setItems] = useState(null);
  const [connectedAccounts, setConnectedAccounts] = useState(null);
  const { refresh: refreshCounts } = useCounts();

  function refresh() {
    studioApi.listStories(status).then(setItems);
  }

  useEffect(refresh, [status]);
  useEffect(() => {
    if (showPublish) socialApi.listAccounts().then(setConnectedAccounts);
  }, [showPublish]);

  async function restore(id) {
    await studioApi.restoreStory(id);
    refresh();
    refreshCounts();
  }

  if (items === null) return null;

  if (items.length === 0) {
    return (
      <div className="empty-block">
        <div className="mark">✦</div>
        <h2>{emptyTitle}</h2>
        <p>{emptySub}</p>
      </div>
    );
  }

  return (
    <div className="item-grid">
      {items.map((s) => (
        <div className="item-card" key={s.id}>
          <video controls preload="metadata" src={studioApi.videoUrl(s.id)} />
          <div className="ic-body">
            <p className="ic-title">{s.title || "Untitled"}</p>
            <p className="ic-meta">
              {formatDuration(s.duration_seconds)} &middot; decided {s.decided_at ? new Date(s.decided_at).toLocaleDateString() : "—"}
            </p>
            <button type="button" className="btn btn-outline" onClick={() => restore(s.id)}>
              <IconRestore />Move back to review
            </button>
            {showPublish && connectedAccounts && (
              <PublishControls storyId={s.id} connectedAccounts={connectedAccounts} />
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
