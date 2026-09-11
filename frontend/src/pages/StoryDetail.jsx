import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import * as studioApi from "../api/studio";
import { useCounts } from "../CountsContext";
import { useToast } from "../ToastContext";
import FactCheck from "../components/FactCheck";
import { IconArrowLeft, IconCheck, IconFilm, IconRestore, IconReview, IconX } from "../components/icons";
import StoryDossier from "../components/StoryDossier";
import { Button, EmptyState, ErrorState, Skeleton, Stamp } from "../components/ui";
import VideoFrame from "../components/VideoFrame";
import { formatDateTime, timeAgo } from "../lib/format";
import { useDocumentTitle, useHotkeys } from "../lib/hooks";

const HOME = {
  approved: { to: "/library", label: "Library" },
  rejected: { to: "/archive", label: "Archive" },
  pending: { to: "/review", label: "Review desk" },
};

/** A single story at its own URL — linkable from anywhere (posters, command menu). */
export default function StoryDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { refresh: refreshCounts } = useCounts();
  const { toast } = useToast();
  const [story, setStory] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);
  const [showVerified, setShowVerified] = useState(false);
  useDocumentTitle(story?.title || "Story");

  const load = useCallback(() => {
    setError(null);
    studioApi.getStory(id).then(setStory).catch(setError);
  }, [id]);
  useEffect(load, [load]);

  useHotkeys({ f: () => setShowVerified((v) => !v) }, { enabled: !!story });

  async function run(kind, fn, success, undo) {
    setBusy(kind);
    try {
      const updated = await fn();
      setStory((s) => ({ ...s, ...updated }));
      refreshCounts();
      toast({ tone: "success", title: success, description: story.title, action: undo && { label: "Undo", onClick: async () => { try { const u = await undo(); setStory((s) => ({ ...s, ...u })); refreshCounts(); } catch (err) { toast({ tone: "error", title: "Couldn’t undo", description: err.message }); } } } });
    } catch (err) {
      toast({ tone: "error", title: "That didn’t save", description: err.message });
    } finally {
      setBusy(null);
    }
  }

  if (error?.status === 404) {
    return (
      <EmptyState icon={IconFilm} title="This story isn’t here." actions={<Link to="/library" className="btn btn-primary">Go to Library</Link>}>
        It may have been removed, or the link is mistyped.
      </EmptyState>
    );
  }
  if (error) return <ErrorState title="The story didn’t load" error={error} onRetry={load} />;

  const home = HOME[story?.status] || HOME.approved;
  const back = () => (window.history.state?.idx > 0 ? navigate(-1) : navigate(home.to));

  return (
    <div className="detail">
      <div className="detail-bar">
        <Button variant="ghost" size="sm" icon={IconArrowLeft} onClick={back}>Back</Button>
        {story && (
          <nav aria-label="Breadcrumb" className="breadcrumb meta">
            <Link to={home.to}>{home.label}</Link>
            <span aria-hidden="true">/</span>
            <span aria-current="page">#{story.id}</span>
          </nav>
        )}
      </div>

      {!story ? (
        <div className="detail-grid" aria-busy="true">
          <div className="frame skeleton" />
          <div>
            <Skeleton width="30%" height={22} />
            <Skeleton width="80%" height={48} style={{ marginTop: 20 }} />
            {Array.from({ length: 6 }, (_, i) => <Skeleton key={i} width={`${92 - i * 5}%`} height={12} style={{ marginTop: 14 }} />)}
          </div>
        </div>
      ) : (
        <div className="detail-grid">
          <div className="detail-stage">
            <VideoFrame story={story} />
          </div>
          <article className="detail-dossier" aria-labelledby="page-title">
            <div className="dossier-status">
              <Stamp status={story.status} />
              {story.decided_at && <span className="meta" title={formatDateTime(story.decided_at)}>Decided {timeAgo(story.decided_at)}</span>}
            </div>
            <StoryDossier story={story} titleId="page-title" />
            <FactCheck story={story} showVerified={showVerified} onToggleVerified={() => setShowVerified((v) => !v)} />

            <div className="decision decision-static" role="group" aria-label="Actions">
              {story.status === "pending" ? (
                <>
                  <p className="muted" style={{ fontSize: "var(--text-sm)" }}>This story is waiting on the review desk.</p>
                  <div className="decision-buttons">
                    <Button variant="secondary" icon={IconX} loading={busy === "reject"} onClick={() => run("reject", () => studioApi.decideStory(story.id, "reject"), "Rejected — moved to Archive", () => studioApi.restoreStory(story.id))}>Reject</Button>
                    <Button variant="primary" icon={IconCheck} loading={busy === "approve"} onClick={() => run("approve", () => studioApi.decideStory(story.id, "approve"), "Approved — moved to Library", () => studioApi.restoreStory(story.id))}>Approve</Button>
                  </div>
                  <Link to={`/review?item=${story.id}`} className="link-button"><IconReview />Open in review desk</Link>
                </>
              ) : (
                <>
                  <p className="muted" style={{ fontSize: "var(--text-sm)" }}>
                    {story.status === "approved" ? "Approved and eligible for publishing." : "Rejected and archived."} Changed your mind?
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
                  </div>
                </>
              )}
            </div>
          </article>
        </div>
      )}
    </div>
  );
}
