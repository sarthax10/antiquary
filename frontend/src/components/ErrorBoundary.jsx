import { Component } from "react";
import { IconAlert } from "./icons";

// Last line of defence: a render error in one page shows a recoverable message instead
// of unmounting the whole app to a blank screen.
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidUpdate(prevProps) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="empty" role="alert">
        <div className="empty-mark" aria-hidden="true"><IconAlert /></div>
        <h2>This page hit a snag.</h2>
        <p>Nothing was lost — your stories are safe on the server. Reloading usually fixes it.</p>
        <div className="empty-actions">
          <button type="button" className="btn btn-primary" onClick={() => window.location.reload()}>Reload page</button>
        </div>
        <details style={{ marginTop: 16, maxWidth: "60ch", color: "var(--ink-muted)", fontSize: 12 }}>
          <summary style={{ cursor: "pointer" }}>Technical details</summary>
          <pre style={{ whiteSpace: "pre-wrap", textAlign: "left", fontFamily: "var(--font-mono)" }}>{String(this.state.error?.stack || this.state.error)}</pre>
        </details>
      </div>
    );
  }
}
