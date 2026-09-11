import { useId } from "react";
import { claimTotals, plural } from "../lib/format";
import { IconAlert, IconCheck, IconChevronDown, IconUncertain } from "./icons";

const VERDICTS = {
  false: { label: "Needs a source", tone: "oxide", Icon: IconAlert, order: 0 },
  uncertain: { label: "Uncertain", tone: "signal", Icon: IconUncertain, order: 1 },
  verified: { label: "Nothing flagged", tone: "patina", Icon: IconCheck, order: 2 },
};

const CONFIDENCE = { low: "Low", medium: "Medium", high: "High" };

function Claim({ claim }) {
  const v = VERDICTS[claim.verdict] || { label: claim.verdict, tone: "neutral", Icon: IconUncertain };
  const { Icon } = v;
  return (
    <li className="claim" data-tone={v.tone}>
      <span className="claim-icon"><Icon /></span>
      <div className="claim-text">
        <span className="claim-verdict">{v.label}</span>
        <p>{claim.claim}</p>
        {claim.note && <p className="claim-note">{claim.note}</p>}
      </div>
    </li>
  );
}

/**
 * Fact-check dossier. Honest by construction: flagged claims come first and are always
 * visible; "verified" is labelled "nothing flagged" because it's the same local model
 * checking itself (see CLAUDE.md), not ground truth.
 */
export default function FactCheck({ story, showVerified, onToggleVerified }) {
  const headingId = useId();
  const listId = useId();
  const { verified, uncertain, flagged, total } = claimTotals(story);
  const claims = story.fact_check?.claims || [];
  const confidence = story.fact_check?.overall_confidence;
  const attention = claims
    .filter((c) => c.verdict !== "verified")
    .sort((a, b) => (VERDICTS[a.verdict]?.order ?? 9) - (VERDICTS[b.verdict]?.order ?? 9));
  const verifiedClaims = claims.filter((c) => c.verdict === "verified");

  return (
    <section className="factcheck" aria-labelledby={headingId}>
      <div className="factcheck-head">
        <h2 id={headingId} className="label">Fact check</h2>
        {confidence && (
          <span className={`badge ${confidence === "low" ? "badge-oxide" : confidence === "medium" ? "badge-signal" : "badge-patina"}`}>
            Model confidence · {CONFIDENCE[confidence] || confidence}
          </span>
        )}
      </div>

      {total === 0 ? (
        <p className="factcheck-caveat">No claims were extracted from this script — read the narration closely before deciding.</p>
      ) : (
        <>
          <div className="fc-summary">
            <div className="fc-bar" aria-hidden="true">
              {flagged > 0 && <span data-tone="oxide" style={{ flexGrow: flagged }} />}
              {uncertain > 0 && <span data-tone="signal" style={{ flexGrow: uncertain }} />}
              {verified > 0 && <span data-tone="patina" style={{ flexGrow: verified }} />}
            </div>
            <p className="fc-legend">
              <span data-tone="oxide"><b>{flagged}</b> need a source</span>
              <span data-tone="signal"><b>{uncertain}</b> uncertain</span>
              <span data-tone="patina"><b>{verified}</b> nothing flagged</span>
              <span className="sr-only">out of {plural(total, "claim")}</span>
            </p>
          </div>

          {attention.length > 0 && (
            <ul className="claims">
              {attention.map((c, i) => <Claim key={`a${i}`} claim={c} />)}
            </ul>
          )}

          {verifiedClaims.length > 0 && (
            <div className="claims-verified">
              <button type="button" className="disclosure" aria-expanded={showVerified} aria-controls={listId} onClick={onToggleVerified}>
                <IconChevronDown />
                {showVerified ? "Hide" : "Show"} {plural(verifiedClaims.length, "claim")} with nothing flagged
                <kbd className="kbd" aria-hidden="true">F</kbd>
              </button>
              <ul className="claims" id={listId} hidden={!showVerified}>
                {verifiedClaims.map((c, i) => <Claim key={`v${i}`} claim={c} />)}
              </ul>
            </div>
          )}

          <p className="factcheck-caveat">
            Checked by a second pass of the same local model. It surfaces doubts; it can’t prove facts — your review is the real check.
          </p>
        </>
      )}
    </section>
  );
}
