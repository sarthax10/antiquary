import { useId, useRef, useState } from "react";
import { Link } from "react-router-dom";
import * as studioApi from "../api/studio";
import { useCounts } from "../CountsContext";
import { useToast } from "../ToastContext";
import FactCheck from "./FactCheck";
import { IconCheck, IconFilm, IconReview, IconRestore, IconX } from "./icons";
import StoryDossier from "./StoryDossier";
import { Button, Dialog, Stamp } from "./ui";
import VideoFrame from "./VideoFrame";

/**
 * A story, watched and decided without leaving the page it was clicked from — used by
 * Create's "recently developed" grid so following up on a render doesn't mean losing
 * your place on the composer. Same dossier/fact-check/decision pieces as the full
 * /stories/:id page (StoryDetail.jsx); this is the popover-sized read of them, with a
 * link out to the full page for anyone who wants it at its own URL.
 */
export default function StoryPreviewModal({ story, onClose, onChange }) {
  const titleId = useId();
  const { refresh: refreshCounts } = useCounts();
  const { toast } = useToast();
  const [busy, setBusy] = useState(null);
  const [showVerified, setShowVerified] = useState(false);
  const closeRef = useRef(null);

  async function run(kind, fn, success, undo) {
    setBusy(kind);
    try {
      const updated = await fn();
      onChange?.(updated);
      refreshCounts();
      toast({
        tone: "success",
        title: success,
        description: story.title,
        action: undo && {
          label: "Undo",
          onClick: async () => {
            try {
              const u = await undo();
              onChange?.(u);
              refreshCounts();
            } catch (err) {
              toast({ tone: "error", title: "Couldn’t undo", description: err.message });
            }
          },
        },
      });
    } catch (err) {
      toast({ tone: "error", title: "That didn’t save", description: err.message });
    } finally {
      setBusy(null);
    }
  }

  return (
    <Dialog open={!!story} onClose={onClose} className="preview" labelledBy={titleId} initialFocusRef={closeRef}>
      {story && (
        <>
          <button ref={closeRef} type="button" className="preview-close" onClick={onClose} aria-label="Close">
            <IconX />
          </button>
          <div className="preview-grid">
            <div className="preview-stage">
              <VideoFrame story={story} />
            </div>
            <div className="preview-dossier">
              <div className="dossier-status">
                <Stamp status={story.status} />
              </div>
              <StoryDossier story={story} titleId={titleId} />
              <FactCheck story={story} showVerified={showVerified} onToggleVerified={() => setShowVerified((v) => !v)} />

              <div className="decision decision-static" role="group" aria-label="Actions">
                {story.status === "pending" ? (
                  <>
                    <p className="muted" style={{ fontSize: "var(--text-sm)" }}>Waiting on the review desk.</p>
                    <div className="decision-buttons">
                      <Button
                        variant="secondary"
                        icon={IconX}
                        loading={busy === "reject"}
                        onClick={() => run("reject", () => studioApi.decideStory(story.id, "reject"), "Rejected — moved to Archive", () => studioApi.restoreStory(story.id))}
                      >
                        Reject
                      </Button>
                      <Button
                        variant="primary"
                        icon={IconCheck}
                        loading={busy === "approve"}
                        onClick={() => run("approve", () => studioApi.decideStory(story.id, "approve"), "Approved — moved to Library", () => studioApi.restoreStory(story.id))}
                      >
                        Approve
                      </Button>
                    </div>
                    <Link to={`/review?item=${story.id}`} className="link-button" onClick={onClose}>
                      <IconReview />Open in review desk
                    </Link>
                  </>
                ) : (
                  <>
                    <p className="muted" style={{ fontSize: "var(--text-sm)" }}>
                      {story.status === "approved" ? "Approved and eligible for publishing." : "Rejected and archived."}
                    </p>
                    <div className="decision-buttons">
                      <Button
                        variant="secondary"
                        icon={IconRestore}
                        loading={busy === "restore"}
                        onClick={() => {
                          const prev = story.status === "approved" ? "approve" : "reject";
                          run("restore", () => studioApi.restoreStory(story.id), "Moved back to the review desk", () => studioApi.decideStory(story.id, prev));
                        }}
                      >
                        Return to review
                      </Button>
                      <Link to={`/stories/${story.id}`} className="link-button" onClick={onClose}>
                        <IconFilm />Open full page
                      </Link>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </Dialog>
  );
}
