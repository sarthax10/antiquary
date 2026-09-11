import { Link } from "react-router-dom";
import { IconMark } from "./icons";

const STEPS = [
  ["01", "Commission", "Give it a direction — or none at all."],
  ["02", "Scrutinise", "Every claim is listed and flagged for doubt."],
  ["03", "Decide", "A human approves each film before it can be published."],
];

/** Two-panel layout for sign-in, request-access and account-status screens. */
export default function AuthLayout({ children, title }) {
  return (
    <div className="auth">
      <aside className="auth-poster" aria-hidden="true">
        <div className="auth-crop auth-crop-tl" />
        <div className="auth-crop auth-crop-br" />
        <div className="auth-poster-top">
          <span className="wordmark"><IconMark className="wordmark-mark" /><span>Antiquary</span></span>
          <span className="label">A studio for short histories</span>
        </div>
        <p className="display auth-poster-title">
          The true stories history forgot, <em>cut to forty seconds.</em>
        </p>
        <ol className="auth-steps">
          {STEPS.map(([n, t, d]) => (
            <li key={n}>
              <span className="meta" style={{ color: "var(--tungsten)" }}>{n}</span>
              <span className="auth-step-title">{t}</span>
              <span className="auth-step-desc">{d}</span>
            </li>
          ))}
        </ol>
      </aside>
      <main className="auth-main" id="main">
        <div className="auth-card page-enter">
          <Link to="/login" className="wordmark auth-mobile-mark" aria-label="Antiquary">
            <IconMark className="wordmark-mark" /><span>Antiquary</span>
          </Link>
          {title}
          {children}
        </div>
        <p className="auth-foot meta">Private studio · access by admin approval</p>
      </main>
    </div>
  );
}
