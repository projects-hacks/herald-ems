import { useEffect, useRef, useState } from "react";
import { Activity, ChevronLeft, FileText, Info, Keyboard, Moon, Settings2, Sun, Users, WifiOff } from "lucide-react";
import { ManualEntry } from "@/components/ManualEntry";
import { EncounterHistory } from "./EncounterControls";
import { PatientRoster } from "@/components/PatientRoster";
import { CaptureBar } from "@/features/capture/CaptureBar";
import { CaptureControl } from "@/features/capture/CaptureControl";
import { alertKey, alertTitle } from "@/lib/selectors";
import { monitorIdle } from "@/features/capture/monitor";
import { ConnectBand, RestoredCallBanner, StaleOverlay } from "@/components/GlobalStates";
import { AttentionQueue } from "@/features/attention/AttentionQueue";
import { useAttention } from "@/hooks/useAttention";
import { patientLine, presence } from "@/lib/copilot";
import { useHerald } from "@/lib/store";
import { PatientPage } from "@/pages/PatientPage";
import { TrendsPage } from "@/pages/TrendsPage";
import { TranscriptPage } from "@/pages/TranscriptPage";
import { HandoffPage } from "@/pages/HandoffPage";
import { MonitorWatch } from "@/features/capture/MonitorWatch";
import { useAmbient } from "./useAmbient";
import { useCaptureOwner } from "./captureOwner";
import "./workspace.css";
import "./capture-workspace.css";
import "../copilot/copilot.css";
import type { WorkspacePanel } from "./WorkspaceNav";
import { EdCard, MovementStrip, PatientBar, PresencePill, ProtocolCues, ReplayBar, SituationBar } from "@/features/copilot/Copilot";
import { HeraldLive } from "@/features/copilot/Live";
import "../copilot/live.css";
import type { FixturePlayer } from "@/lib/ws";

// One screen. Everything that is not "Now" opens from the control that needs it (the ED card opens the handoff, the
// dock opens typing, the header opens the record, protocol search and settings) and closes back to Now.
type Panel = Exclude<WorkspacePanel, "trends" | "protocols" | "camera"> | "record";
type RecordView = "facts" | "trends" | "transcript";
const TITLES = { review: "Needs you", patient: "Patient record", record: "Record", patients: "Patients", notes: "Type a note", handoff: "ED handoff", settings: "Settings" };

export function CabinApp({ player }: { player?: FixturePlayer | null } = {}) {
  const s = useHerald((st) => st.snapshot);
  const ui = useHerald((st) => st.ui);
  const source = useHerald((st) => st.source);
  const health = useHerald((st) => st.health);
  const stale = useHerald((st) => st.stale || st.conn !== "open");
  const setUi = useHerald((st) => st.setUi);
  const a = useAttention();
  useCaptureOwner();                        // one tab listens and watches; others only show the call
  const elsewhere = useHerald((st) => st.captureElsewhere);
  const ambient = useAmbient();
  const [panel, setPanel] = useState<Panel>(null);
  const [recordView, setRecordView] = useState<RecordView>("facts");
  const [monitor, setMonitor] = useState(monitorIdle);
  const page = useRef<HTMLElement>(null);
  const lastTrigger = useRef<HTMLElement | null>(null);
  const urgentLive = useRef<HTMLSpanElement>(null);
  const announced = useRef<Set<string>>(new Set());
  useEffect(() => { announced.current.clear(); if (urgentLive.current) urgentLive.current.textContent = ""; }, [s?.incident.id]);   // a new incident starts a fresh announcement slate
  useEffect(() => {   // announce each urgent alert once, when it arrives; the queue's own assertive region announces too
    const fresh = (a?.urgent ?? []).filter((al) => !announced.current.has(alertKey(al)));
    for (const al of fresh) announced.current.add(alertKey(al));
    if (fresh.length && urgentLive.current) urgentLive.current.textContent = fresh.map(alertTitle).join(" · ");
  }, [a, s?.incident.id]);
  const open = (value: Panel) => { if (!panel) lastTrigger.current = document.activeElement as HTMLElement; setPanel(value); if (!value) requestAnimationFrame(() => document.getElementById("workspace-main")?.focus()); };
  const close = () => { setPanel(null); requestAnimationFrame(() => (lastTrigger.current?.isConnected ? lastTrigger.current : document.getElementById("workspace-main"))?.focus()); };
  useEffect(() => { if (panel) { page.current?.focus({ preventScroll: true }); page.current?.scrollIntoView?.({ block: "start" }); } }, [panel]);
  const patientKey = s ? `${s.incident.id}|${s.active_patient}` : null;
  const lastPatient = useRef<string | null>(null);
  useEffect(() => {   // a different patient returns to Now; the first snapshot (a deep link, a reload) does not
    if (patientKey && lastPatient.current && lastPatient.current !== patientKey) setPanel(null);
    if (patientKey) lastPatient.current = patientKey;
  }, [patientKey]);
  useEffect(() => {   // hotkeys and older links still name pages; they land in the record's matching view
    if (ui.page === "overview") return;
    if (ui.page === "patient" || ui.page === "trends") { setRecordView(ui.page === "trends" ? "trends" : "facts"); setPanel("record"); }
    else setPanel(ui.page === "transcript" ? "notes" : ui.page);
    setUi({ page: "overview" });
  }, [ui.page, setUi]);
  const openRecord = (view: RecordView) => { setRecordView(view); open("record"); };
  const recording = ambient.status.listening || ambient.status.starting;
  const isReplay = source === "fixture";
  const pill = presence({ replay: isReplay, elsewhere, offline: stale, hasSnapshot: !!s, health,
    listening: ambient.status.listening, micError: ambient.status.error ? ambient.status.message : null,
    monitorWatching: !!(monitor.active || (s?.capture?.auto && s.capture.sees !== "off")),
    cameraError: s?.capture?.error ?? (monitor.error ? monitor.message : null) });
  const multi = (s?.patients?.length ?? 0) > 1;
  return <div className={`cabin workspace-shell copilot ${panel ? "workspace-task" : ""} ${ui.typeScale > 1 ? "cabin-large-text" : ""}`}><div className="workspace-body">
    <header className="copilot-header">
      {panel ? <button className="copilot-back" onClick={close} aria-label="Back to now"><ChevronLeft size={18} />Now</button>
        : <span className="copilot-mark" aria-label="Herald"><Activity size={22} strokeWidth={2.6} aria-hidden /></span>}
      <div className="copilot-patient"><h1>{s ? patientLine(s) : "Waiting for the vehicle"}</h1>{s && <span className="encounter-reference">{s.patients?.find((p) => p.id === s.incident.id)?.label || "Patient"} · {s.incident.id.slice(-6)} · {s.incident.ended_at ? "Finished" : s.incident.transferred_at ? "Care transferred" : s.incident.arrived_at ? "At destination" : "In ambulance"}</span>}</div>
      {panel && <PresencePill p={pill} paused={ui.capturePaused} disabled={isReplay || ambient.blocked}
        onToggle={() => setUi({ capturePaused: !ui.capturePaused })} />}   {/* on Now, Herald's orb is the control */}
      {isReplay && player && <ReplayBar player={player} />}
      <div className="copilot-header-actions">
        {s?.capture?.auto && <CaptureControl stopOnly />}   {/* the vehicle's connected camera: a direct stop */}
        <button className="cabin-button" aria-label="Type a note" aria-pressed={panel === "notes"} onClick={() => open("notes")}><Keyboard size={19} /></button>
        <button className="cabin-button" aria-label="Record" aria-pressed={panel === "record"} onClick={() => openRecord("facts")}><FileText size={19} /><span className="patients-button-label">Record</span></button>
        {<button className="cabin-button" aria-label="Patients" onClick={() => open("patients")}><Users size={19} /><span className="patients-button-label">Patients</span></button>}
        <button className="cabin-button" aria-label={ui.theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          onClick={() => setUi({ theme: ui.theme === "dark" ? "light" : "dark" })}>{ui.theme === "dark" ? <Sun size={19} /> : <Moon size={19} />}</button>
        <button className="cabin-button" aria-label="Settings" onClick={() => open("settings")}><Settings2 size={19} /></button>
      </div>
      {!panel && <PatientBar onDetails={() => openRecord("facts")} />}   {/* the patient, as a bar: safety facts first */}
      {!panel && <SituationBar />}
    </header>
    <div className="cabin-sticky-status"><ConnectBand /><StaleOverlay /><RestoredCallBanner />{multi && <PatientRoster />}</div>
    <main id="workspace-main" tabIndex={-1} className="cabin-main">
      <span ref={urgentLive} className="sr-only" role="alert" />
      {/* Now, laid out like an instrument panel: the medic's decisions (Needs you) get the tallest, most stable
          region at the top left; Herald's live view, how the patient is moving and what the ED has sit beside it;
          the county's words for this situation have their own column on wide screens. What Herald did is a record
          of the system, not of the patient, so it is on the Record page, not here. */}
      {!panel && s?.incident.ended_at && <section className="encounter-card"><h2>Encounter finished</h2><p>Capture has stopped. The record and any authorized ED delivery remain available.</p><div className="cabin-actions"><button className="cabin-button" onClick={() => open("handoff")}>Review handoff</button><button className="cabin-button" onClick={() => open("patients")}>Patients and next encounter</button></div></section>}
      <div hidden={!!panel || !!s?.incident.ended_at} className="copilot-grid">
        <div className="copilot-primary"><AttentionQueue className="copilot-needs" /></div>
        <div className="copilot-rest">
          <div className="copilot-side copilot-side-live">
            {!panel && !s?.incident.ended_at && <HeraldLive p={pill} paused={ui.capturePaused} disabled={isReplay || ambient.blocked} level={ambient.status.level}
              waitingTap={!!ambient.status.waitingTap} warning={ambient.status.warning} monitor={monitor}
              onToggle={() => setUi({ capturePaused: !ui.capturePaused })} />}
            <MovementStrip onTrends={() => openRecord("trends")} />
            <EdCard onHandoff={() => open("handoff")} />
          </div>
          <div className="copilot-side copilot-side-protocol">{!panel && <ProtocolCues />}</div>
        </div>
      </div>
      <section hidden={!panel} ref={page} tabIndex={-1} className="workspace-page" aria-label={panel ? TITLES[panel] : undefined}>
        {!s && panel && ["review", "patient", "record", "patients", "handoff"].includes(panel) ? <div className="workspace-page-surface workspace-page-unavailable" role="status">
          <WifiOff size={28} aria-hidden /><h1 className="workspace-page-heading">{TITLES[panel]}</h1><p>Patient data is not available yet. This page will update when the vehicle connects.</p>
        </div> : <>
          {panel === "review" && <AttentionQueue />}
          {(panel === "patient" || panel === "record") && <div className="copilot-record">
            <div className="copilot-segments" role="tablist" aria-label="Record views">
              {([["facts", "Facts & sources"], ["trends", "Trends & scores"], ["transcript", "What Herald did"]] as const).map(([v, label]) =>
                <button key={v} role="tab" aria-selected={recordView === v} onClick={() => setRecordView(v)}>{label}</button>)}
            </div>
            {(recordView === "facts" || panel === "patient") && <PatientPage />}
            {recordView === "trends" && panel === "record" && <TrendsPage />}
            {recordView === "transcript" && panel === "record" && <TranscriptPage onReview={() => open(null)} />}
          </div>}
          {panel === "patients" && <div className="workspace-page-surface"><h1 className="workspace-page-heading">Patients</h1><PatientRoster expanded /><EncounterHistory /></div>}
          {panel === "handoff" && <HandoffPage />}
        </>}
        {panel === "notes" && <><div className="copilot-notes-tools"><ManualEntry key={s?.incident.id} /></div><TranscriptPage onReview={() => open(null)} /><CaptureBar allowVoice={!recording && ambient.status.queued === 0} /></>}
        {/* The camera watches with the call and follows the header's pause; no screen of its own (owner, 2026-09-26). */}
        <div hidden><MonitorWatch key={s?.incident.id} onStatus={setMonitor} /></div>
        {panel === "settings" && <div className="cabin-settings workspace-page-surface"><h1 className="workspace-page-heading">Settings</h1>
          <div className="cabin-actions">{([1, 1.25, 1.5] as const).map((scale) => <button className="cabin-button" key={scale} aria-pressed={ui.typeScale === scale} onClick={() => setUi({ typeScale: scale })}>Text {scale * 100}%</button>)}
            <button className="cabin-button" onClick={() => setUi({ theme: ui.theme === "dark" ? "light" : "dark" })}>{ui.theme === "dark" ? <Sun size={20} /> : <Moon size={20} />}{ui.theme === "dark" ? "Daylight theme" : "Night theme"}</button></div>
          <label className="copilot-switch"><input type="checkbox" checked={ui.autoCapture} onChange={(e) => setUi({ autoCapture: e.target.checked, capturePaused: !e.target.checked })} />
            Listen and watch automatically when a call starts</label>
          <div className="cabin-actions"><button className="cabin-button" onClick={() => open("patients")}>Patients and encounters</button>
            <button className="cabin-button" onClick={() => setUi({ presentationMode: true })}>Guided demo</button><button className="cabin-button" onClick={() => setUi({ mode: "explain" })}>Detailed application view</button></div>
          <details><summary><Info size={18} />Recording, privacy and what runs in the background</summary><p>Record only when authorized. After you start listening, Herald listens continuously and sends only speech, cut at natural pauses, to this vehicle’s server; everything is processed on the vehicle. Speaker identity is not detected. Every captured fact needs your confirmation before it counts toward scores or is shared.</p><p>Monitor watch keeps the camera on the equipment while you use other pages; the vehicle keeps useful stills and holds readings for your confirmation. Capture continues while this tab is in the background. If the vehicle server is unreachable, speech waits in this page and is retried; after about a minute of waiting, or if a clip keeps failing, the oldest words are skipped and Herald says so. Pausing, changing patient or leaving the page stops capture; waiting audio is not a durable backup. Handoff delivery status is a system acknowledgment, not proof a clinician has read it.</p></details>
          <p className="cabin-muted">Prototype. Not validated for use during patient care.</p>
        </div>}
      </section>
    </main>
  </div></div>;
}
