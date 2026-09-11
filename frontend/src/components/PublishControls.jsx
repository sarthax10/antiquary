import { useEffect, useState } from "react";
import * as publishApi from "../api/publish";

const PLATFORM_LABEL = { youtube: "YouTube", instagram: "Instagram" };

export default function PublishControls({ storyId, connectedAccounts }) {
  const [publications, setPublications] = useState(null);

  function refresh() {
    publishApi.listPublications(storyId).then(setPublications);
  }

  useEffect(refresh, [storyId]);

  useEffect(() => {
    if (!publications?.some((p) => p.status === "pending" || p.status === "uploading")) return;
    const timer = setInterval(refresh, 2500);
    return () => clearInterval(timer);
  }, [publications, storyId]);

  async function publish(platform) {
    await publishApi.startPublish(storyId, platform);
    refresh();
  }

  if (publications === null) return null;
  if (connectedAccounts.length === 0) {
    return <p className="ic-meta publish-hint">Connect an account to publish.</p>;
  }

  // publications is newest-first; Object.fromEntries keeps the LAST entry for a
  // repeated key, so build it from the reversed (oldest-first) array — otherwise a
  // second attempt (e.g. a retry) would silently lose to the first one's stale status.
  const byPlatform = Object.fromEntries([...publications].reverse().map((p) => [p.platform, p]));

  return (
    <div className="publish-row">
      {connectedAccounts.map((account) => {
        const pub = byPlatform[account.platform];
        const label = PLATFORM_LABEL[account.platform] || account.platform;

        if (!pub || pub.status === "failed") {
          return (
            <button
              key={account.platform}
              type="button"
              className="btn btn-outline btn-publish"
              title={pub?.error || ""}
              onClick={() => publish(account.platform)}
            >
              {pub ? `Retry ${label}` : `Publish to ${label}`}
            </button>
          );
        }
        if (pub.status === "published") {
          return (
            <a key={account.platform} className="publish-status publish-status-done" href={pub.external_url} target="_blank" rel="noreferrer">
              Published to {label}
            </a>
          );
        }
        return (
          <span key={account.platform} className="publish-status publish-status-pending">
            {label}: {pub.stage || pub.status}…
          </span>
        );
      })}
    </div>
  );
}
