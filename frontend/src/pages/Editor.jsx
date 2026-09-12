import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import * as editorApi from "../api/editor";
import * as studioApi from "../api/studio";
import { useToast } from "../ToastContext";
import { IconArrowLeft, IconEdit, IconFilm, IconLayers, IconRefresh } from "../components/icons";
import { Button, EmptyState, ErrorState, Skeleton } from "../components/ui";
import { formatDuration } from "../lib/format";
import { useDocumentTitle } from "../lib/hooks";

/**
 * The first real, visible slice of the timeline editor (Phase B — see Claude outputs/
 * OPEN_ISSUES.md #3). Deliberately narrow: shows a story's timeline as track lists, lets
 * a human edit one caption's text, and re-renders from the edited timeline. Not the full
 * trim/reorder/swap-clip editor in the roadmap — this proves the render-from-timeline
 * path works end to end from a real UI before more editing operations are built on it.
 */
export default function Editor() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [story, setStory] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [error, setError] = useState(null);
  const [editingCap, setEditingCap] = useState(null);
  const [draftText, setDraftText] = useState("");
  const [savingCap, setSavingCap] = useState(null);
  const [renderStatus, setRenderStatus] = useState({ status: "idle" });
  const pollRef = useRef(null);
  useDocumentTitle(story ? `Edit — ${story.title}` : "Edit story");

  const load = useCallback(() => {
    setError(null);
    Promise.all([studioApi.getStory(id), editorApi.getTimeline(id)])
      .then(([s, t]) => {
        setStory(s);
        setTimeline(t.timeline);
        setRenderStatus(t.render);
      })
      .catch(setError);
  }, [id]);
  useEffect(load, [load]);

  // While a re-render is in flight, poll status until it settles — same "cheap polling,
  // no separate push infrastructure" approach the generation status bar already uses.
  useEffect(() => {
    if (renderStatus.status !== "rendering") {
      clearInterval(pollRef.current);
      return;
    }
    pollRef.current = setInterval(() => {
      editorApi.getRenderStatus(id).then((s) => {
        setRenderStatus(s);
        if (s.status === "done") {
          toast({ tone: "success", title: "Re-render complete", description: "The video has been updated." });
          studioApi.getStory(id).then(setStory);
        } else if (s.status === "error") {
          toast({ tone: "error", title: "Re-render failed", description: s.error || "Unknown error." });
        }
      });
    }, 2500);
    return () => clearInterval(pollRef.current);
  }, [renderStatus.status, id, toast]);

  async function saveCaption(capId) {
    setSavingCap(capId);
    try {
      const updated = await editorApi.updateCaption(id, capId, draftText);
      setTimeline(updated);
      setEditingCap(null);
      toast({ tone: "success", title: "Caption updated" });
    } catch (err) {
      toast({ tone: "error", title: "Couldn’t save", description: err.message });
    } finally {
      setSavingCap(null);
    }
  }

  async function rerender() {
    try {
      const res = await editorApi.startRender(id);
      if (res.started) {
        setRenderStatus({ status: "rendering", error: null });
        toast({ title: "Re-rendering…", description: "This can take a minute or two." });
      } else {
        toast({ tone: "error", title: "Couldn’t start", description: res.message });
      }
    } catch (err) {
      toast({ tone: "error", title: "Couldn’t start", description: err.message });
    }
  }

  if (error?.status === 404) {
    return (
      <EmptyState icon={IconFilm} title="This story isn’t here." actions={<Link to="/library" className="btn btn-primary">Go to Library</Link>}>
        It may have been removed, or the link is mistyped.
      </EmptyState>
    );
  }
  if (error) return <ErrorState title="The editor didn’t load" error={error} onRetry={load} />;

  return (
    <div className="detail">
      <div className="detail-bar">
        <Button variant="ghost" size="sm" icon={IconArrowLeft} onClick={() => navigate(story ? `/stories/${story.id}` : "/library")}>Back</Button>
      </div>

      {!story || !timeline ? (
        <div aria-busy="true">
          <Skeleton width="40%" height={32} />
          <Skeleton width="100%" height={200} style={{ marginTop: 20 }} />
        </div>
      ) : !timeline.tracks ? (
        <EmptyState icon={IconLayers} title="No timeline for this story yet">
          This story was rendered before the timeline editor existed, so there's nothing
          to edit here.
        </EmptyState>
      ) : (
        <div className="editor-page">
          <div className="editor-head">
            <h1 className="h2">{story.title}</h1>
            <Button
              variant="primary"
              icon={IconRefresh}
              loading={renderStatus.status === "rendering"}
              disabled={renderStatus.status === "rendering"}
              onClick={rerender}
            >
              {renderStatus.status === "rendering" ? "Re-rendering…" : "Re-render"}
            </Button>
          </div>
          {renderStatus.status === "error" && (
            <p className="editor-render-error">Last re-render failed: {renderStatus.error}</p>
          )}

          <section className="editor-section">
            <h2 className="label">Visual track</h2>
            <ol className="editor-clip-list">
              {timeline.tracks.visual.map((clip) => (
                <li key={clip.id} className="editor-clip">
                  <span className="editor-clip-kind">{clip.kind}</span>
                  <span className="editor-clip-query">{clip.visual_query}</span>
                  <span className="meta">{formatDuration(clip.duration)}</span>
                </li>
              ))}
            </ol>
          </section>

          <section className="editor-section">
            <h2 className="label">Captions</h2>
            <ol className="editor-caption-list">
              {timeline.tracks.captions.map((cap) => (
                <li key={cap.id} className="editor-caption">
                  {editingCap === cap.id ? (
                    <div className="editor-caption-edit">
                      <input
                        className="input"
                        value={draftText}
                        onChange={(e) => setDraftText(e.target.value)}
                        autoFocus
                        onKeyDown={(e) => {
                          if (e.key === "Enter") saveCaption(cap.id);
                          if (e.key === "Escape") setEditingCap(null);
                        }}
                      />
                      <Button size="sm" variant="primary" loading={savingCap === cap.id} onClick={() => saveCaption(cap.id)}>Save</Button>
                      <Button size="sm" variant="ghost" onClick={() => setEditingCap(null)}>Cancel</Button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      className="editor-caption-text"
                      onClick={() => { setEditingCap(cap.id); setDraftText(cap.text); }}
                    >
                      <IconEdit /> {cap.text}
                    </button>
                  )}
                </li>
              ))}
            </ol>
          </section>
        </div>
      )}
    </div>
  );
}
