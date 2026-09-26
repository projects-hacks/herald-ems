// States every live screen handles: connecting, can't connect, stale, toast, and the
// new-incident confirmation. The replay controls live in the sidebar.
import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { useContract } from "@/lib/contract";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { clockTime, hhmmss } from "@/lib/format";
import { useHerald } from "@/lib/store";
import { OutcomeChoice } from "@/features/cabin/EncounterControls";
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
  const s = useHerald((st) => st.snapshot);
  const disabled = useHerald((st) => st.stale || st.conn !== "open" || st.source !== "live");
  const setUi = useHerald((st) => st.setUi);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  if (!s?.restored || s.incident.ended_at) return null;
  return <div role="status" className="encounter-recovery">
    <p>Saved encounter restored · {s.incident.id.slice(-6)}. Capture is paused until you confirm this is the patient in the ambulance.</p>
    <div className="cabin-actions"><button className="cabin-button" disabled={disabled || busy} onClick={async () => {
      setBusy(true); setError(""); if (!await api.resumeEncounter()) setError("Could not resume. Review the connection and retry."); setBusy(false);
    }}>Continue with this patient</button>
    <button className="cabin-button" onClick={() => setUi({ page: "handoff" })}>Review handoff</button>
    <button className="cabin-button" disabled={disabled || busy} onClick={() => setUi({ confirmNewIncident: true })}>Finish and start next…</button></div>
    {error && <p role="alert">{error}</p>}
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
  const persisted = useHerald((s) => s.snapshot?.history_persisted);
  const stillOpen = useHerald((s) => !!s.snapshot && !s.snapshot.incident.ended_at);   // this encounter needs its outcome
  const [outcome, setOutcome] = useState<string | null>(null);
  useEffect(() => { if (open) { setDispatch(""); setError(""); setOutcome(null); } }, [open]);
  const capturing = useHerald((s) => s.ui.heldAlerts);
  const blocked = useHerald((s) => s.stale || s.conn !== "open" || s.source === "fixture");
  return (
    <Dialog open={open} onOpenChange={(o) => setUi({ confirmNewIncident: o })}>
      <DialogContent>
        <DialogTitle>Finish this encounter and start the next?</DialogTitle>
        <DialogDescription>This stops capture and removes this scene’s audio and photos. Unprocessed capture will not be added. Structured patient records and existing authorized ED delivery stay available in Previous encounters. The next patient starts with a fresh record and needs a new ED authorization. This does not record transfer of care. To include another patient at this scene, use Add patient at this scene.</DialogDescription>
        {!persisted && <p role="alert">Local recovery is off. Download the handoff before restarting the server.</p>}
        {stillOpen && <OutcomeChoice value={outcome} onChange={setOutcome} />}
        <button type="button" className="min-h-12 text-left text-body text-herald-accent" onClick={() => setUi({ confirmNewIncident: false, page: "handoff" })}>Review or download the handoff first</button>
        <label className="text-body">Dispatch / call type<input list="dispatch-types" value={dispatch} onChange={(e) => setDispatch(e.target.value)} placeholder="Unspecified, or type dispatch" className="mt-2 block min-h-12 w-full rounded-lg border border-border-control bg-surface-2 px-3" /></label>
        <datalist id="dispatch-types">{Object.entries(contract?.checklists ?? {}).filter(([, c]) => c.label).map(([id, c]) => <option key={id} value={id}>{c.label}</option>)}</datalist>
        {error && <p role="alert">{error}</p>}
        <DialogFooter>
          <button type="button" onClick={() => setUi({ confirmNewIncident: false })} className="min-h-12 rounded-[var(--radius-control)] border border-border-subtle bg-surface-2 px-4 text-button font-semibold">Cancel</button>
          <button type="button" disabled={busy || capturing || blocked || (stillOpen && !outcome)} onClick={async () => { setBusy(true); if (await api.newIncident(dispatch.trim() || null, stillOpen ? outcome : null)) setUi({ confirmNewIncident: false, incidentPhase: "scene", page: "overview" }); else setError("Could not start a new incident. Check the current patient before retrying."); setBusy(false); }}
            className="min-h-16 rounded-[var(--radius-control)] bg-accent-fill px-4 text-button font-semibold text-on-accent-fill">Finish and start next</button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function EndIncidentDialog() {
  const open = useHerald((s) => s.ui.confirmEndIncident);
  const setUi = useHerald((s) => s.setUi);
  const disabled = useHerald((s) => s.stale || s.conn !== "open" || s.source !== "live");
  const persisted = useHerald((s) => s.snapshot?.history_persisted);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [outcome, setOutcome] = useState<string | null>(null);
  useEffect(() => { if (open) { setError(""); setOutcome(null); } }, [open]);
  return <Dialog open={open} onOpenChange={(o) => setUi({ confirmEndIncident: o })}><DialogContent>
    <DialogTitle>Finish this encounter?</DialogTitle>
    <DialogDescription>Capture stops and this patient’s audio and photos are deleted. Unprocessed capture will not be added. The structured record and authorized ED delivery remain available. Other patients at this scene stay open. Finishing does not record transfer of care.</DialogDescription>
    {!persisted && <p role="alert">Local recovery is off. Download the handoff before restarting the server.</p>}
    <OutcomeChoice value={outcome} onChange={setOutcome} />
    {error && <p role="alert">{error}</p>}
    <DialogFooter>
      <button className="cabin-button" disabled={busy} onClick={() => setUi({ confirmEndIncident: false })}>Cancel</button>
      <button className="cabin-button primary" disabled={disabled || busy || !outcome} onClick={async () => {
        if (!outcome) return;
        setBusy(true); if (await api.finishEncounter(outcome)) setUi({ confirmEndIncident: false });
        else setError("Could not finish the encounter. Check its status before retrying."); setBusy(false);
      }}>Finish encounter</button>
    </DialogFooter>
  </DialogContent></Dialog>;
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
