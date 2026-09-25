// A last line of defense for render errors (docs/API_CONTRACT.md: every screen handles its failure states): instead of a
// blank screen mid-call, show a plain card and a way to reload. Patient data lives on the vehicle, not in this view.
import { Component, type ErrorInfo, type ReactNode } from "react";

export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Herald display error", error, info.componentStack);
  }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="grid min-h-dvh place-items-center bg-bg p-6">
        <div role="alert" className="card flex max-w-md flex-col items-center gap-3 p-6 text-center">
          <p className="text-title font-semibold text-text-primary">Display error</p>
          <p className="text-body text-text-muted">This display hit an error and stopped updating. Patient data stays on the vehicle server; reloading does not lose it.</p>
          <button type="button" onClick={() => window.location.reload()}
            className="min-h-12 rounded-[var(--radius-control)] bg-accent-fill px-4 text-button font-semibold text-on-accent-fill">Reload display</button>
        </div>
      </div>
    );
  }
}
