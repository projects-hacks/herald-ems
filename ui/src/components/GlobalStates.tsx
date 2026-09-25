// States every live screen handles: connecting, can't connect, stale, toast, and the
// new-incident confirmation. The replay controls live in the sidebar.
import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { useContract } from "@/lib/contract";
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

export function RestoredCallBanner() {
  const restored = useHerald((s) => s.snapshot?.restored === true);
  if (!restored) return null;
  return <div role="status" className="mx-5 mt-4 rounded-[14px] bg-low-tint px-4 py-3 text-body font-semibold text-low-fg">
    Unfinished call restored from encrypted local recovery state. Review the active patient and relay status before continuing.
  </div>;
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
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const contract = useContract();
  useEffect(() => { if (open) { setDispatch(""); setError(""); } }, [open]);
  const capturing = useHerald((s) => s.ui.heldAlerts);
  const blocked = useHerald((s) => s.stale || s.conn !== "open" || s.source === "fixture");
  return (
    <Dialog open={open} onOpenChange={(o) => setUi({ confirmNewIncident: o })}>
      <DialogContent>
        <DialogTitle>Start a new incident?</DialogTitle>
        <DialogDescription>This ends the current call, permanently deletes its audio and photos, replaces the entire active patient roster, and resets the ED relay. To add someone to this incident, use Add patient instead.</DialogDescription>
        <button type="button" className="min-h-12 text-left text-body text-herald-accent" onClick={() => setUi({ confirmNewIncident: false, page: "handoff" })}>Review or download the handoff first</button>
        <label className="text-body">Dispatch / call type<input list="dispatch-types" value={dispatch} onChange={(e) => setDispatch(e.target.value)} placeholder="Unspecified — or type dispatch" className="mt-2 block min-h-12 w-full rounded-lg border border-border-control bg-surface-2 px-3" /></label>
        <datalist id="dispatch-types">{Object.entries(contract?.checklists ?? {}).filter(([, c]) => c.label).map(([id, c]) => <option key={id} value={id}>{c.label}</option>)}</datalist>
        {error && <p role="alert">{error}</p>}
        <DialogFooter>
          <button type="button" onClick={() => setUi({ confirmNewIncident: false })} className="min-h-12 rounded-[var(--radius-control)] border border-border-subtle bg-surface-2 px-4 text-button font-semibold">Cancel</button>
          <button type="button" disabled={busy || capturing || blocked} onClick={async () => { setBusy(true); if (await api.newIncident(dispatch.trim() || null)) setUi({ confirmNewIncident: false, incidentPhase: "scene", page: "overview" }); else setError("Could not start a new incident. Your current call remains on screen."); setBusy(false); }}
            className="min-h-16 rounded-[var(--radius-control)] bg-accent-fill px-4 text-button font-semibold text-on-accent-fill">Start new incident</button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function EndIncidentDialog() {
  const open = useHerald((s) => s.ui.confirmEndIncident);
  const setUi = useHerald((s) => s.setUi);
  return (
    <Dialog open={open} onOpenChange={(o) => setUi({ confirmEndIncident: o })}>
      <DialogContent>
        <DialogTitle>End this call?</DialogTitle>
        <DialogDescription>This permanently deletes this call&apos;s audio and photos. Patient facts remain on screen for review until you start a new incident.</DialogDescription>
        <DialogFooter>
          <button type="button" onClick={() => setUi({ confirmEndIncident: false })} className="min-h-12 rounded-[var(--radius-control)] border border-border-subtle bg-surface-2 px-4 text-button font-semibold">Cancel</button>
          <button type="button" onClick={async () => { if (await api.endIncident()) setUi({ confirmEndIncident: false }); }}
            className="min-h-16 rounded-[var(--radius-control)] bg-accent-fill px-4 text-button font-semibold text-on-accent-fill">End call and delete media</button>
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
  const btn = "min-h-12 rounded-[var(--radius-control)] bg-surface-2 px-3.5 text-button font-semibold hover:bg-surface-3";
  return (
    <div className="fixed inset-x-4 bottom-4 z-40 flex flex-wrap items-center gap-2 rounded-[22px] bg-surface-1/95 px-4 py-3 shadow-[var(--shadow-3)] backdrop-blur-xl" role="region" aria-label="Presenter">
      <span className="text-meta font-semibold text-text-secondary">Presenter</span>
      <button type="button" className={btn} onClick={() => setUi({ presentationMode: !ui.presentationMode })}>{ui.presentationMode ? "Clinical view" : "Guided demo"}</button>
      <button type="button" className={btn} onClick={() => setUi({ mode: ui.mode === "medic" ? "explain" : "medic" })}>{ui.mode === "medic" ? "Explain mode" : "Medic mode"}</button>
      <button type="button" className={btn} onClick={() => setUi({ theme: ui.theme === "dark" ? "light" : "dark" })}>Theme: {ui.theme}</button>
      <button type="button" className={btn} onClick={() => setUi({ typeScale: ui.typeScale === 1 ? 1.25 : ui.typeScale === 1.25 ? 1.5 : 1 })}>Text size {ui.typeScale}×</button>
      <button type="button" className={btn} aria-pressed={ui.reducedMotion} onClick={() => setUi({ reducedMotion: !ui.reducedMotion })}>Reduce motion: {ui.reducedMotion ? "on" : "off"}</button>
      <button type="button" className={btn} onClick={() => setUi({ confirmEndIncident: true })}>End call</button>
      <button type="button" className={btn} onClick={() => setUi({ confirmNewIncident: true })}>New incident</button>
      <button type="button" className={`${btn} ml-auto`} onClick={() => setUi({ presenterOpen: false })}>Close (`)</button>
    </div>
  );
}
