// States every live screen handles (UX_PLAN §3.0, §3.1.12): connecting, can't connect, stale, toast, and the
// new-incident confirmation. The replay controls live in the sidebar.
import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { clockTime, hhmmss } from "@/lib/format";
import { useHerald } from "@/lib/store";
import { CANT_CONNECT_MS } from "@/lib/ws";
import { useNow } from "@/hooks/useNow";

export function ConnectBand() {
  const conn = useHerald((s) => s.conn);
  const since = useHerald((s) => s.connectingSince);
  const has = useHerald((s) => s.snapshot !== null);
  const source = useHerald((s) => s.source);
  useNow();
  if (source === "fixture" || conn === "open" || has) return null;
  const long = performance.now() - since > CANT_CONNECT_MS;
  return (
    <div role="status" className="mx-5 mt-4 rounded-[14px] bg-surface-1 px-4 py-3 text-body">
      {long ? `Can't reach the Herald server at ${location.host}. Retrying every 2 s. Is it running?` : "Connecting to Herald on this vehicle…"}
    </div>
  );
}

export function StaleOverlay() {
  const stale = useHerald((s) => s.stale);
  const at = useHerald((s) => s.lastStateAt);
  const now = useNow();
  if (!stale) return null;
  return (
    <div className="mx-5 my-2 shrink-0 motion-safe:animate-in motion-safe:fade-in" role="alert">
      <p className="mx-auto flex max-w-3xl items-center gap-3 rounded-[16px] bg-low-tint px-4 py-3 text-body font-semibold text-low-fg shadow-[var(--shadow-3)]">
        <RefreshCw size={19} aria-hidden className="shrink-0" />
        <span><span className="text-text-primary">Connection interrupted. Showing the last received patient picture.</span> Last update {clockTime(at)} ({hhmmss((now - at) / 1000)} ago). Changes are paused while reconnecting. This view is not a saved backup.</span>
      </p>
    </div>
  );
}

export function Toast() {
  const t = useHerald((s) => s.toast);
  useEffect(() => {
    if (!t) return;
    const id = window.setTimeout(() => useHerald.setState({ toast: null }), 3000);
    return () => window.clearTimeout(id);
  }, [t]);
  if (!t) return null;
  return <div role="status" className="fixed bottom-24 left-1/2 z-50 -translate-x-1/2 rounded-full bg-surface-2 px-5 py-2.5 text-body font-medium shadow-[var(--shadow-3)]">{t.text}</div>;
}

export function NewIncidentDialog() {
  const open = useHerald((s) => s.ui.confirmNewIncident);
  const setUi = useHerald((s) => s.setUi);
  const [dispatch, setDispatch] = useState("");
  const capturing = useHerald((s) => s.ui.heldAlerts);
  const blocked = useHerald((s) => s.stale || s.conn !== "open" || s.source === "fixture");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) setDispatch(""); }, [open]);
  return (
    <Dialog open={open} onOpenChange={(o) => setUi({ confirmNewIncident: o })}>
      <DialogContent>
        <DialogTitle>Start a new incident?</DialogTitle>
        <DialogDescription>This replaces the current patient and resets the ED relay. The current prototype has no incident archive. Starting a new incident will make this record unavailable from this screen.</DialogDescription>
        <button type="button" className="text-left text-body font-semibold text-herald-accent" onClick={() => setUi({ confirmNewIncident: false, page: "handoff" })}>Review or download the handoff draft first</button>
        <label className="flex flex-col gap-2 text-body">New dispatch reference
          <input value={dispatch} onChange={(e) => setDispatch(e.target.value)} placeholder="New call reference or leave blank" className="h-12 rounded-xl border border-border-control bg-surface-2 px-3" />
        </label>
        {capturing && <p role="status" className="text-body text-low-fg">Finish recording before changing patients.</p>}
        <DialogFooter>
          <button type="button" onClick={() => setUi({ confirmNewIncident: false })} className="min-h-11 rounded-[var(--radius-control)] bg-surface-2 px-4 text-button font-semibold hover:bg-surface-3">Cancel</button>
          <button type="button" disabled={capturing || blocked || busy} onClick={async () => { setBusy(true); try { if (await api.newIncident(dispatch.trim() || null)) setUi({ confirmNewIncident: false, incidentPhase: "scene", page: "overview" }); } finally { setBusy(false); } }}
            className="min-h-11 rounded-[var(--radius-control)] bg-accent-fill px-4 text-button font-semibold text-on-accent-fill">Start new incident</button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Presenter bar (` key). U8 adds the link buttons and the county switch; this has the screen settings. */
export function PresenterBar() {
  const ui = useHerald((s) => s.ui);
  const setUi = useHerald((s) => s.setUi);
  if (!ui.presenterOpen) return null;
  const btn = "min-h-11 rounded-[var(--radius-control)] bg-surface-2 px-3.5 text-button font-semibold hover:bg-surface-3";
  return (
    <div className="fixed inset-x-4 bottom-4 z-40 flex flex-wrap items-center gap-2 rounded-[22px] bg-surface-1/95 px-4 py-3 shadow-[var(--shadow-3)] backdrop-blur-xl" role="region" aria-label="Presenter">
      <span className="text-meta font-semibold text-text-secondary">Presenter</span>
      <button type="button" className={btn} onClick={() => setUi({ presentationMode: !ui.presentationMode })}>{ui.presentationMode ? "Clinical view" : "Guided demo"}</button>
      <button type="button" className={btn} onClick={() => setUi({ mode: ui.mode === "medic" ? "explain" : "medic" })}>{ui.mode === "medic" ? "Explain mode" : "Medic mode"}</button>
      <button type="button" className={btn} onClick={() => setUi({ theme: ui.theme === "dark" ? "light" : "dark" })}>Theme: {ui.theme}</button>
      <button type="button" className={btn} onClick={() => setUi({ typeScale: ui.typeScale === 1 ? 1.25 : ui.typeScale === 1.25 ? 1.5 : 1 })}>Text size {ui.typeScale}×</button>
      <button type="button" className={btn} aria-pressed={ui.reducedMotion} onClick={() => setUi({ reducedMotion: !ui.reducedMotion })}>Reduce motion: {ui.reducedMotion ? "on" : "off"}</button>
      <button type="button" className={btn} onClick={() => setUi({ confirmNewIncident: true })}>New incident</button>
      <button type="button" className={`${btn} ml-auto`} onClick={() => setUi({ presenterOpen: false })}>Close (`)</button>
    </div>
  );
}
