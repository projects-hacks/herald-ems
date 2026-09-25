import { useEffect, useRef, useState } from "react";
import { Activity, BookOpen, Camera, ChevronRight, FileText, Info, Keyboard, Mic, Moon, Pause, Settings2, Sun, Users, WifiOff } from "lucide-react";
import { ManualEntry } from "@/components/ManualEntry";
import { PatientRoster } from "@/components/PatientRoster";
import { CaptureBar } from "@/features/capture/CaptureBar";
import { CaptureControl } from "@/features/capture/CaptureControl";
import { ProtocolSearch } from "@/features/protocols/ProtocolSearch";
import { alertKey, alertTitle } from "@/lib/selectors";
import { monitorIdle } from "@/features/capture/monitor";
import { ConnectBand, RestoredCallBanner, StaleOverlay } from "@/components/GlobalStates";
import { AttentionQueue } from "@/features/attention/AttentionQueue";
import { StatTiles } from "@/features/overview/StatTiles";
import { useAttention } from "@/hooks/useAttention";
import { patientLabel } from "@/lib/format";
import { patientLine, presence } from "@/lib/copilot";
import { useHerald } from "@/lib/store";
import { PatientPage } from "@/pages/PatientPage";
import { TrendsPage } from "@/pages/TrendsPage";
import { TranscriptPage } from "@/pages/TranscriptPage";
import { HandoffPage } from "@/pages/HandoffPage";
import type { CameraStatus } from "./CameraCapture";
import { CameraWorkspace } from "./CameraWorkspace";
import { useAmbient } from "./useAmbient";
import { VitalReadings } from "./VitalReadings";
import "./workspace.css";
import "./capture-workspace.css";
import "../copilot/copilot.css";
import type { WorkspacePanel } from "./WorkspaceNav";
import { CareSummary, PatientSafetySummary } from "./CareSummary";
import { EdCard, HeraldActivity, MovementStrip, PresencePill, ProtocolCues, ReplayBar } from "@/features/copilot/Copilot";
import type { FixturePlayer } from "@/lib/ws";

// One screen. Everything that is not "Now" opens from the control that needs it (the ED card opens the handoff, the
// dock opens the camera and typing, the header opens the record, protocol search and settings) and closes back to Now.
type Panel = Exclude<WorkspacePanel, "trends" | "protocols"> | "record";
type RecordView = "facts" | "trends" | "transcript";
const TITLES = { review: "Needs you", patient: "Patient record", record: "Record", patients: "Patients", notes: "Type a note", handoff: "ED handoff", camera: "Camera", settings: "Settings" };

export function CabinApp({ player }: { player?: FixturePlayer | null } = {}) {
  const s = useHerald((st) => st.snapshot);
  const ui = useHerald((st) => st.ui);
  const source = useHerald((st) => st.source);
  const health = useHerald((st) => st.health);
  const stale = useHerald((st) => st.stale || st.conn !== "open");
  const setUi = useHerald((st) => st.setUi);
  const a = useAttention();
  const ambient = useAmbient();
  const [panel, setPanel] = useState<Panel>(null);
  const [recordView, setRecordView] = useState<RecordView>("facts");
  const [protocols, setProtocols] = useState(false);
  const [photo, setPhoto] = useState<CameraStatus>({ active: false, busy: false, message: "", failed: false });
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
  useEffect(() => { setPanel(null); }, [s?.incident.id, s?.active_patient]);
  useEffect(() => {   // hotkeys and older links still name pages; they land in the record's matching view
    if (ui.page === "overview") return;
    if (ui.page === "patient" || ui.page === "trends") { setRecordView(ui.page === "trends" ? "trends" : "facts"); setPanel("record"); }
    else setPanel(ui.page === "transcript" ? "notes" : ui.page);
    setUi({ page: "overview" });
  }, [ui.page, setUi]);
  const openRecord = (view: RecordView) => { setRecordView(view); open("record"); };
  const recording = ambient.status.listening || ambient.status.starting;
  const identity = s?.facts["patient.name"];
  const isReplay = source === "fixture";
  const pill = presence({ replay: isReplay, offline: stale, hasSnapshot: !!s, health,
    listening: ambient.status.listening, micError: ambient.status.error ? ambient.status.message : null,
    monitorWatching: !!(monitor.active || (s?.capture?.auto && s.capture.sees !== "off")),
    cameraError: s?.capture?.error ?? (monitor.error ? monitor.message : null) });
  const multi = (s?.patients?.length ?? 0) > 1;
  return <div className={`cabin workspace-shell copilot ${panel ? "workspace-task" : ""} ${panel === "camera" ? "workspace-camera" : ""} ${ui.typeScale > 1 ? "cabin-large-text" : ""}`}><div className="workspace-body">
    <header className="copilot-header">
      {panel ? <button className="copilot-back" onClick={close} aria-label="Back to now"><ChevronRight size={18} className="rotate-180" />Now</button>
        : <span className="copilot-mark" aria-label="Herald"><Activity size={22} strokeWidth={2.6} aria-hidden /></span>}
      <h1 className="copilot-patient">{s ? patientLine(s) : "Waiting for the vehicle"}</h1>
      <PresencePill p={pill} />
      {isReplay && player && <ReplayBar player={player} />}
      <div className="copilot-header-actions">
        <button className="cabin-button" aria-label="Record" aria-pressed={panel === "record"} onClick={() => openRecord("facts")}><FileText size={19} /><span className="patients-button-label">Record</span></button>
        <button className="cabin-button" aria-label="Protocols" onClick={() => setProtocols(true)}><BookOpen size={19} /><span className="patients-button-label">Protocols</span></button>
        {multi && <button className="cabin-button" aria-label="Patients" onClick={() => open("patients")}><Users size={19} /><span className="patients-button-label">Patients</span></button>}
        <button className="cabin-button" aria-label="Settings" onClick={() => open("settings")}><Settings2 size={19} /></button>
      </div>
    </header>
    <div className="cabin-sticky-status"><ConnectBand /><StaleOverlay /><RestoredCallBanner />{multi && <PatientRoster />}</div>
    <main id="workspace-main" tabIndex={-1} className="cabin-main">
      <span ref={urgentLive} className="sr-only" role="alert" />
      <div hidden={!!panel} className="copilot-grid">
        <div className="copilot-primary"><PatientSafetySummary onReview={() => openRecord("facts")} /><AttentionQueue className="copilot-needs" /></div>
        <div className="copilot-side">
          <ProtocolCues onOpen={() => setProtocols(true)} />
          <HeraldActivity onAll={() => openRecord("transcript")} />
          <MovementStrip onTrends={() => openRecord("trends")} />
          <EdCard onHandoff={() => open("handoff")} />
        </div>
      </div>
      <section hidden={!panel} ref={page} tabIndex={-1} className="workspace-page" aria-label={panel ? TITLES[panel] : undefined}>
        {!s && panel && ["review", "patient", "record", "patients", "handoff"].includes(panel) ? <div className="workspace-page-surface workspace-page-unavailable" role="status">
          <WifiOff size={28} aria-hidden /><h1 className="workspace-page-heading">{TITLES[panel]}</h1><p>Patient data is not available yet. This page will update when the vehicle connects.</p>
        </div> : <>
          {panel === "review" && <AttentionQueue />}
          {(panel === "patient" || panel === "record") && <div className="copilot-record">
            <div className="copilot-segments" role="tablist" aria-label="Record views">
              {([["facts", "Facts & sources"], ["trends", "Trends & scores"], ["transcript", "Transcript"]] as const).map(([v, label]) =>
                <button key={v} role="tab" aria-selected={recordView === v} onClick={() => setRecordView(v)}>{label}</button>)}
            </div>
            {(recordView === "facts" || panel === "patient") && <PatientPage />}
            {recordView === "trends" && panel === "record" && <><StatTiles /><VitalReadings key={s?.active_patient ?? s?.incident.id} onReview={() => open(null)} onTrends={() => setRecordView("trends")} /><CareSummary onReview={() => open(null)} /><TrendsPage /></>}
            {recordView === "transcript" && panel === "record" && <TranscriptPage onReview={() => open(null)} />}
          </div>}
          {panel === "patients" && <div className="workspace-page-surface"><h1 className="workspace-page-heading">Manage patients</h1><PatientRoster /></div>}
          {panel === "handoff" && <HandoffPage />}
        </>}
        {panel === "notes" && <><div className="copilot-notes-tools"><ManualEntry key={s?.incident.id} /></div><TranscriptPage onReview={() => open(null)} /><CaptureBar allowVoice={!recording && ambient.status.queued === 0} /></>}
        <div hidden={panel !== "camera"}><CameraWorkspace key={s?.incident.id} patient={identity?.status === "confirmed" ? String(identity.value) : s?.summary?.split(" · ")[0] || patientLabel(s)} visible={panel === "camera"} onStatus={setPhoto} onMonitorStatus={setMonitor} onReview={() => open(null)} /></div>
        {panel === "settings" && <div className="cabin-settings workspace-page-surface"><h1 className="workspace-page-heading">Settings</h1>
          <div className="cabin-actions">{([1, 1.25, 1.5] as const).map((scale) => <button className="cabin-button" key={scale} aria-pressed={ui.typeScale === scale} onClick={() => setUi({ typeScale: scale })}>Text {scale * 100}%</button>)}
            <button className="cabin-button" onClick={() => setUi({ theme: ui.theme === "dark" ? "light" : "dark" })}>{ui.theme === "dark" ? <Sun size={20} /> : <Moon size={20} />}{ui.theme === "dark" ? "Daylight theme" : "Night theme"}</button></div>
          <div className="cabin-actions"><button className="cabin-button" onClick={() => setProtocols(true)}>Search protocols</button>
            <button className="cabin-button" disabled={recording || ambient.status.queued > 0 || photo.busy} onClick={() => setUi({ confirmNewIncident: true })}>New incident…</button>
            <button className="cabin-button" onClick={() => setUi({ presentationMode: true })}>Guided demo</button><button className="cabin-button" onClick={() => setUi({ mode: "explain" })}>Detailed application view</button></div>
          <details><summary><Info size={18} />Recording, privacy and what runs in the background</summary><p>Record only when authorized. After you start listening, audio is captured continuously and sent in about 8-second clips to this vehicle’s server; everything is processed on the vehicle. Speaker identity is not detected. Every captured fact needs your confirmation before it counts toward scores or is shared.</p><p>Monitor watch keeps the camera on the equipment while you use other pages; the vehicle keeps useful stills and holds readings for your confirmation. Hiding this tab, changing patient, losing the connection or leaving the workspace stops capture. Unsent audio is not a durable backup. Handoff delivery status is a system acknowledgment, not proof a clinician has read it.</p></details>
          <p className="cabin-muted">Prototype. Not validated for use during patient care.</p>
        </div>}
      </section>
    </main>
    <footer className="copilot-dock">
      {s?.capture?.auto && <CaptureControl stopOnly />}
      <button className={`cabin-button copilot-mic ${recording ? "recording" : "primary"}`} disabled={ambient.blocked || (!recording && ui.heldAlerts)}
        style={recording ? { ["--level" as string]: String(Math.min(1, ambient.status.level * 4)) } : undefined}
        onClick={() => recording ? ambient.pause() : void ambient.start()}>
        {recording ? <Pause size={24} /> : <Mic size={24} />}{ambient.status.listening ? "Listening — pause" : ambient.status.starting ? "Starting…" : "Start listening"}
        {ambient.status.queued > 0 && <span className="sr-only">{ambient.status.queued} clips processing</span>}</button>
      {panel !== "camera" && <button className="cabin-button" onClick={() => open("camera")}><Camera size={23} />Camera</button>}
      {panel !== "notes" && <button className="cabin-button" onClick={() => open("notes")}><Keyboard size={21} />Type</button>}
    </footer>
    <ProtocolSearch open={protocols} onClose={() => setProtocols(false)} />
  </div></div>;
}
