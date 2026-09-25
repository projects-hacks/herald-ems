// States every live screen handles (UX_PLAN §3.0, §3.1.12): connecting, can't connect, stale, toast, and the
// new-incident confirmation. The replay controls live in the sidebar.
import { RefreshCw } from "lucide-react";
import { useEffect } from "react";
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
    <div role="status" className="mx-5 mt-4 rounded-[12px] border border-border-subtle bg-surface-2 px-4 py-2.5 text-body">
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
    <div className="absolute inset-0 z-[60] grid place-items-center bg-scrim backdrop-blur-sm motion-safe:animate-in motion-safe:fade-in" role="alert">
      <p className="inline-flex items-center gap-2 rounded-[16px] bg-surface-3 px-6 py-4 text-critical text-text-primary shadow-[var(--shadow-3)]">
        <RefreshCw size={20} aria-hidden />Screen not updating. Last update {clockTime(at)} ({hhmmss((now - at) / 1000)} ago). Reconnecting…
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
  return <div role="status" className="fixed bottom-16 left-1/2 z-50 -translate-x-1/2 rounded-full bg-surface-3 px-5 py-2.5 text-body font-medium shadow-[var(--shadow-3)]">{t.text}</div>;
}

export function NewIncidentDialog() {
  const open = useHerald((s) => s.ui.confirmNewIncident);
  const setUi = useHerald((s) => s.setUi);
  const dispatch = useHerald((s) => s.snapshot?.incident.dispatch ?? null);
  return (
    <Dialog open={open} onOpenChange={(o) => setUi({ confirmNewIncident: o })}>
      <DialogContent>
        <DialogTitle>Start a new incident?</DialogTitle>
        <DialogDescription>This ends the current call, permanently deletes its audio and photos, clears the patient from this screen, and resets the ED relay.</DialogDescription>
        <DialogFooter>
          <button type="button" onClick={() => setUi({ confirmNewIncident: false })} className="min-h-11 rounded-[var(--radius-control)] border border-border-subtle bg-surface-2 px-4 text-button font-semibold">Cancel</button>
          <button type="button" onClick={async () => { if (await api.newIncident(dispatch)) setUi({ confirmNewIncident: false }); }}
            className="min-h-11 rounded-[var(--radius-control)] bg-accent-fill px-4 text-button font-semibold text-on-accent-fill">Start new incident</button>
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
          <button type="button" onClick={() => setUi({ confirmEndIncident: false })} className="min-h-11 rounded-[var(--radius-control)] border border-border-subtle bg-surface-2 px-4 text-button font-semibold">Cancel</button>
          <button type="button" onClick={async () => { if (await api.endIncident()) setUi({ confirmEndIncident: false }); }}
            className="min-h-11 rounded-[var(--radius-control)] bg-accent-fill px-4 text-button font-semibold text-on-accent-fill">End call and delete media</button>
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
  const btn = "min-h-11 rounded-[var(--radius-control)] border border-border-subtle bg-surface-2 px-3 text-button font-semibold hover:bg-surface-1";
  return (
    <div className="fixed inset-x-4 bottom-4 z-40 flex flex-wrap items-center gap-2 rounded-[18px] border border-border-subtle bg-surface-3/95 px-4 py-3 shadow-[var(--shadow-3)] backdrop-blur-md" role="region" aria-label="Presenter">
      <span className="text-meta font-semibold text-text-secondary">Presenter</span>
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
