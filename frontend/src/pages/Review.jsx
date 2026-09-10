import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import * as studioApi from "../api/studio";
import { useCounts } from "../CountsContext";
import { IconCheck, IconChevronL, IconChevronR, IconUncertain, IconX } from "../components/icons";

const VERDICT_META = {
  verified: { color: "var(--success)", label: "Verified", Icon: IconCheck },
  uncertain: { color: "var(--gold)", label: "Uncertain", Icon: IconUncertain },
  false: { color: "var(--destructive)", label: "Needs source", Icon: IconX },
};

function ClaimRow({ claim }) {
  const meta = VERDICT_META[claim.verdict] || { color: "var(--ink-muted)", label: claim.verdict, Icon: IconUncertain };
  const { Icon } = meta;
  return (
    <li className="claim-row">
      <span className="claim-verdict-mark" style={{ color: meta.color }}><Icon /></span>
      <div>
        <p><strong style={{ color: meta.color }}>{meta.label}.</strong> {claim.claim}</p>
        <p className="note">{claim.note}</p>
      </div>
    </li>
  );
}

function formatDuration(seconds) {
  if (seconds == null) return "—";
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export default function Review() {
  const [items, setItems] = useState(null);
  const [index, setIndex] = useState(0);
  const [claimsExpanded, setClaimsExpanded] = useState(false);
  const [searchParams] = useSearchParams();
  const videoRef = useRef(null);
  const { refresh: refreshCounts } = useCounts();

  useEffect(() => {
    studioApi.listStories("pending").then((stories) => {
      setItems(stories);
      const itemParam = searchParams.get("item");
      if (itemParam) {
        const found = stories.findIndex((s) => s.id === itemParam);
        if (found >= 0) setIndex(found);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const total = items?.length ?? 0;
  const current = items && total > 0 ? items[Math.min(index, total - 1)] : null;

  const decide = useCallback(
    async (action) => {
      if (!current) return;
      await studioApi.decideStory(current.id, action);
      setItems((prev) => prev.filter((s) => s.id !== current.id));
      setClaimsExpanded(false);
      setIndex((i) => Math.min(i, Math.max(0, total - 2)));
      refreshCounts();
    },
    [current, total, refreshCounts]
  );

  const goNext = useCallback(() => setIndex((i) => Math.min(i + 1, total - 1)), [total]);
  const goPrev = useCallback(() => setIndex((i) => Math.max(i - 1, 0)), []);

  useEffect(() => {
    function onKeyDown(e) {
      if (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT") return;
      if (e.key === "a" || e.key === "A") decide("approve");
      else if (e.key === "r" || e.key === "R") decide("reject");
      else if (e.key === "n" || e.key === "N") goNext();
      else if (e.key === "p" || e.key === "P") goPrev();
      else if (e.key === "f" || e.key === "F") setClaimsExpanded((v) => !v);
      else if (e.key === " ") {
        e.preventDefault();
        const v = videoRef.current;
        if (v) v.paused ? v.play() : v.pause();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [decide, goNext, goPrev]);

  const claimCounts = useMemo(() => current?.claim_counts || { verified: 0, uncertain: 0, false: 0 }, [current]);
  const nClaims = claimCounts.verified + claimCounts.uncertain + claimCounts.false;

  if (items === null) return null;

  if (total === 0) {
    return (
      <div className="empty-block">
        <div className="mark">✦</div>
        <h2>Your queue is clear.</h2>
        <p>Nothing is waiting for your eye right now.</p>
        <a href="/create" className="btn btn-gold">Generate a story</a>
      </div>
    );
  }

  return (
    <>
      <div className="review-top">
        <span className="review-count">REVIEW {index + 1} / {total}</span>
        <div className="review-nav">
          <button type="button" className="btn btn-ghost" onClick={goPrev} disabled={index === 0}><IconChevronL /></button>
          <button type="button" className="btn btn-ghost" onClick={goNext} disabled={index >= total - 1}><IconChevronR /></button>
        </div>
      </div>
      <div className="review-grid">
        <div>
          <div className="review-video">
            <video ref={videoRef} controls preload="metadata" src={studioApi.videoUrl(current.id)} />
          </div>
          <div className="review-video-meta">
            <span>{formatDuration(current.duration_seconds)}</span>
            <span>9:16</span>
          </div>
        </div>
        <div className="review-story">
          <h1>{current.title || "Untitled"}</h1>
          <p className="review-hook">&ldquo;{current.hook}&rdquo;</p>
          <p className="section-label">Story</p>
          <p className="review-narration">{current.narration}</p>

          <p className="section-label">Fact check</p>
          <div className="factcheck-summary">
            <div className="fc-count">{nClaims}</div>
            <div className="fc-breakdown">
              <span><span className="fc-dot" style={{ background: "var(--success)" }} />{claimCounts.verified} verified</span>
              <span><span className="fc-dot" style={{ background: "var(--gold)" }} />{claimCounts.uncertain} uncertain</span>
              <span><span className="fc-dot" style={{ background: "var(--destructive)" }} />{claimCounts.false} needs source</span>
            </div>
          </div>
          <button type="button" className="claims-toggle" onClick={() => setClaimsExpanded((v) => !v)}>
            {claimsExpanded ? "Hide claims (F)" : "Show claims (F)"}
          </button>
          {claimsExpanded && (
            <ul className="claims-list expanded">
              {(current.fact_check?.claims || []).map((c, i) => <ClaimRow key={i} claim={c} />)}
              {(!current.fact_check?.claims || current.fact_check.claims.length === 0) && (
                <li className="claim-row">No claims extracted.</li>
              )}
            </ul>
          )}

          <div className="review-actions">
            <button type="button" className="btn btn-outline" onClick={() => decide("reject")}><IconX />Reject</button>
            <button type="button" className="btn btn-gold" onClick={() => decide("approve")}><IconCheck />Approve &amp; Next</button>
          </div>
          <div className="kbd-hint">
            <span><kbd>A</kbd> approve</span><span><kbd>R</kbd> reject</span>
            <span><kbd>N</kbd>/<kbd>P</kbd> next/prev</span><span><kbd>Space</kbd> play</span><span><kbd>F</kbd> claims</span>
          </div>
          <div className="system-meta">
            #{current.id} &middot; {new Date(current.created_at).toLocaleString()}
          </div>
        </div>
      </div>
    </>
  );
}
