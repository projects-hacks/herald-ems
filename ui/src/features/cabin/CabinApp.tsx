import { useEffect, useRef, useState } from "react";
import { BookOpen, Camera, ChevronRight, CircleCheck, CircleDashed, Clock3, FileText, Info, Keyboard, MapPin, Mic, MicOff, Moon, OctagonAlert, Pause, Settings2, Sun, TriangleAlert, UserRound, Users, WifiOff } from "lucide-react";
import { ManualEntry } from "@/components/ManualEntry";
import { PatientRoster } from "@/components/PatientRoster";
import { CompactStatus } from "@/components/CompactStatus";
import { CaptureControl } from "@/features/capture/CaptureControl";
import { CaptureBar } from "@/features/capture/CaptureBar";
import { ProtocolSearch } from "@/features/protocols/ProtocolSearch";
import { alertKey, alertTitle, allFacts, queuedCount } from "@/lib/selectors";
import { ConnectBand, RestoredCallBanner, StaleOverlay } from "@/components/GlobalStates";
import { AttentionQueue } from "@/features/attention/AttentionQueue";
import { StatTiles } from "@/features/overview/StatTiles";
import { useAttention } from "@/hooks/useAttention";
import { useNow } from "@/hooks/useNow";
import { clockSeconds, hhmm, hhmmss, patientLabel } from "@/lib/format";
import { useHerald, type IncidentPhase } from "@/lib/store";
import { PatientPage } from "@/pages/PatientPage";
import { TrendsPage } from "@/pages/TrendsPage";
import { TranscriptPage } from "@/pages/TranscriptPage";
import { HandoffPage } from "@/pages/HandoffPage";
import type { CameraStatus } from "./CameraCapture";
import { CameraWorkspace } from "./CameraWorkspace";
import { useAmbient } from "./useAmbient";
import { VitalReadings } from "./VitalReadings";
import { WorkspaceCards } from "./WorkspaceCards";
import "./cabin.css";
import "./workspace.css";
import "./medic.css";
import "./capture-workspace.css";
import { WorkspaceNav, type WorkspacePanel } from "./WorkspaceNav";
import { CareSummary, PatientSafetySummary } from "./CareSummary";
import { ProtocolLibrary } from "./ProtocolLibrary";
import type { FixturePlayer } from "@/lib/ws";

type Panel = WorkspacePanel;
const TITLES = { review: "Review captured information", patient: "Patient record & sources", patients: "Manage patients", trends: "Readings, trends & scores", notes: "Captured notes & processing", handoff: "Receiving-team handoff", camera: "Capture visual evidence", settings: "Workspace settings", protocols: "Protocol library" };

export function CabinApp({ player }: { player?: FixturePlayer | null } = {}) {
  const s = useHerald((st) => st.snapshot);
  const ui = useHerald((st) => st.ui);
  const source = useHerald((st) => st.source);
  const health = useHerald((st) => st.health);
  const stale = useHerald((st) => st.stale || st.conn !== "open");
  const at = useHerald((st) => st.lastStateAt);
  const setUi = useHerald((st) => st.setUi);
  const a = useAttention();
  const now = useNow();
  const ambient = useAmbient();
  const [panel, setPanel] = useState<Panel>(null);
  const [protocols, setProtocols] = useState(false);
  const [photo, setPhoto] = useState<CameraStatus>({ active: false, busy: false, message: "", failed: false });
  const page = useRef<HTMLElement>(null);
  const lastTrigger = useRef<HTMLElement | null>(null);
  const urgentLive = useRef<HTMLSpanElement>(null);
  const announced = useRef<Set<string>>(new Set());
  useEffect(() => { announced.current.clear(); if (urgentLive.current) urgentLive.current.textContent = ""; }, [s?.incident.id]);   // a new incident starts a fresh announcement slate
  useEffect(() => {   // announce each urgent alert once, when it arrives; the review panel's own assertive region already announces there
    const fresh = (a?.urgent ?? []).filter((al) => !announced.current.has(alertKey(al)));
    for (const al of fresh) announced.current.add(alertKey(al));
    if (fresh.length && panel !== "review" && urgentLive.current) urgentLive.current.textContent = fresh.map(alertTitle).join(" · ");
  }, [a, panel, s?.incident.id]);
  const open = (value: Panel) => { if (!panel) lastTrigger.current = document.activeElement as HTMLElement; setPanel(value); if (!value) requestAnimationFrame(() => document.getElementById("workspace-main")?.focus()); };
  const close = () => { setPanel(null); requestAnimationFrame(() => (lastTrigger.current?.isConnected ? lastTrigger.current : document.getElementById("cabin-attention"))?.focus()); };
  useEffect(() => { if (panel) { page.current?.focus({ preventScroll: true }); page.current?.scrollIntoView?.({ block: "start" }); } }, [panel]);
  useEffect(() => { setPanel(null); }, [s?.incident.id, s?.active_patient]);
  useEffect(() => { if (ui.page !== "overview") { setPanel(ui.page === "transcript" ? "notes" : ui.page); setUi({ page: "overview" }); } }, [ui.page, setUi]);
  const recording = ambient.status.listening || ambient.status.starting;
  const elapsed = s?.clocks.find((c) => c.id === "scene");
  const identity = s?.facts["patient.name"];
  const destination = s?.facts["transport.destination"];
  const latest = s?.transcripts.at(-1);
  const proposed = s ? allFacts(s).filter((f) => f.status === "unconfirmed").length : 0;
  const processing = s?.transcripts.filter((t) => t.trace.model.status === "running").length ?? 0;
  const errors = s?.transcripts.filter((t) => t.trace.model.status === "error").length ?? 0;
  const firstAlert = a ? a.urgent[0] ?? a.choose[0] ?? a.confirmAlerts[0] ?? a.review[0] : undefined;
  const headline = firstAlert ? alertTitle(firstAlert) : undefined;
  const isReplay = source === "fixture";
  // The extraction model being down means new speech silently stops becoming facts: the banner escalates to HIGH.
  const modelDown = !isReplay && health?.llm_available === false;
  const cameraState = s?.capture?.sees ?? "status unavailable";
  return <div className={`cabin workspace-shell ${panel ? "workspace-task" : ""} ${panel === "camera" ? "workspace-camera" : ""} ${ui.typeScale > 1 ? "cabin-large-text" : ""}`}><WorkspaceNav panel={panel} onOpen={open} count={a?.count ?? 0} player={player} /><div className="workspace-body">
    <header className="cabin-header">
      <div className="workspace-breadcrumb">{panel ? <button onClick={close} aria-label="Back to overview">Overview</button> : <span>Care workspace</span>}<ChevronRight size={15} /><strong>{panel ? TITLES[panel] : "Overview"}</strong></div>
      <div className="cabin-phase" role="group" aria-label="Workspace phase, this screen only">
        {(["scene", "transport", "handoff"] as IncidentPhase[]).map((phase) => <button key={phase} aria-pressed={ui.incidentPhase === phase}
          onClick={() => { setUi({ incidentPhase: phase }); if (phase === "handoff") open("handoff"); }}><span className="phase-dot" />{phase === "scene" ? "On scene" : phase === "transport" ? "In transit" : "Handoff"}</button>)}
      </div>
      <div className="cabin-header-actions">
        <button className="cabin-button" aria-label="Protocols" onClick={() => setProtocols(true)}><BookOpen size={20} /><span className="patients-button-label">Protocols</span></button>
        <button className="cabin-button" aria-label="Patients" onClick={() => open("patients")}><Users size={19} /><span className="patients-button-label">Patients</span></button>
        <button className="cabin-button" aria-label={ui.theme === "dark" ? "Use daylight theme" : "Use night theme"} onClick={() => setUi({ theme: ui.theme === "dark" ? "light" : "dark" })}>{ui.theme === "dark" ? <Sun size={21} /> : <Moon size={21} />}</button>
        <button className="cabin-button workspace-settings-shortcut" aria-label="Workspace settings" onClick={() => open("settings")}><Settings2 size={19} /></button>
      </div>
    </header>
    <div className="cabin-sticky-status">
      <div className="cabin-patient-context"><span className="workspace-patient-pin"><UserRound size={14} />{identity?.status === "confirmed" ? String(identity.value) : s?.summary?.split(" · ")[0] || patientLabel(s)}</span><CompactStatus always /><span className="workspace-session"><Clock3 size={14} />Started {hhmm(s?.incident.started)}</span></div>
      <ConnectBand /><StaleOverlay />
      <RestoredCallBanner />
      {isReplay && <p className="cabin-replay">Demo replay · recorded scenario, not a live patient · capture disabled</p>}
    </div>
    <main id="workspace-main" tabIndex={-1} className="cabin-main">
      <section hidden={!!panel} className="cabin-patient" aria-label="Current patient">
        <div className="patient-identity"><span className="patient-avatar"><UserRound size={30} strokeWidth={1.6} /></span><div><p className="cabin-eyebrow">CURRENT PATIENT <span className="encounter-badge">{isReplay ? "Recorded encounter" : s ? "Active encounter" : "Awaiting connection"}</span></p>
          <h1>{identity?.status === "confirmed" ? String(identity.value) : patientLabel(s)}</h1>
          <p>{s?.summary || "Start capture or enter a patient fact"}</p>
          <p className="cabin-muted">{identity?.status !== "confirmed" ? "Identity not confirmed · " : ""}{s?.incident.dispatch ? `Dispatch: ${s.incident.dispatch}` : "Dispatch not recorded"}</p>
          {(s?.patients?.length ?? 0) > 1 && <PatientRoster />}
        </div></div>
        <div className="cabin-journey"><span><Clock3 size={14} />CALL ELAPSED</span><strong>{elapsed ? hhmmss(clockSeconds(elapsed, at, now)) : "—"}</strong>
          <p><MapPin size={14} />{destination?.status === "confirmed" ? String(destination.value) : "Destination not confirmed"}</p></div>
      </section>
      <PatientSafetySummary onReview={() => open("patient")} />
      <button id="cabin-attention" className={`cabin-attention ${modelDown || a?.urgent.length ? "urgent" : ""} ${modelDown || a?.count ? "has-items" : ""}`} disabled={!s} onClick={() => open("review")}>
        {!s ? <CircleDashed size={22} aria-hidden /> : modelDown || a?.urgent.length ? <OctagonAlert size={22} aria-hidden className="flash-high" /> : a?.count ? <TriangleAlert size={22} aria-hidden /> : <CircleCheck size={22} aria-hidden />}
        <span><strong>{!s ? "Waiting for patient data" : modelDown ? "Extraction model not running — new speech will not become facts" : headline ?? (proposed ? `${proposed} captured facts need verification` : "No open review items")}</strong>
          <small>{!s ? "Review will be available when the vehicle connects" : modelDown ? headline ?? "Captured words are kept · enter facts by hand until the model returns" : a?.urgent.length ? `${a.urgent.length} high-priority finding(s) · open review` : headline ? "Open review for evidence and details" : "Missing information is not a normal finding"}</small></span>
        <span className="cabin-count">{s ? a?.count ?? 0 : "—"}<small>to review</small></span><ChevronRight size={23} aria-hidden />
      </button>
      <span ref={urgentLive} className="sr-only" role="alert" />
      <div hidden={!!panel}><StatTiles overview /></div>
      <div hidden={!!panel}><VitalReadings key={s?.active_patient ?? s?.incident.id} onReview={() => open("review")} onTrends={() => open("trends")} /></div>
      <section hidden={!panel} ref={page} tabIndex={-1} className="workspace-page" aria-label={panel ? TITLES[panel] : undefined}>
        {!s && panel && ["review", "patient", "patients", "trends", "handoff"].includes(panel) ? <div className="workspace-page-surface workspace-page-unavailable" role="status">
          <WifiOff size={28} aria-hidden /><h1 className="workspace-page-heading">{TITLES[panel]}</h1><p>Patient data is not available yet. This page will update when the vehicle connects.</p>
        </div> : <>
          {panel === "review" && <AttentionQueue />}
          {panel === "patient" && <PatientPage />}
          {panel === "patients" && <div className="workspace-page-surface"><h1 className="workspace-page-heading">Manage patients</h1><PatientRoster /></div>}
          {panel === "trends" && <><StatTiles /><TrendsPage /></>}
          {panel === "handoff" && <HandoffPage />}
        </>}
        {panel === "notes" && <><TranscriptPage onReview={() => open("review")} /><CaptureBar allowVoice={!recording && ambient.status.queued === 0} /></>}
        {panel === "protocols" && <div className="workspace-page-surface"><h1 className="workspace-page-heading">Protocol library</h1><ProtocolLibrary /></div>}
        <div hidden={panel !== "camera"}><CameraWorkspace key={s?.incident.id} patient={identity?.status === "confirmed" ? String(identity.value) : s?.summary?.split(" · ")[0] || patientLabel(s)} visible={panel === "camera"} onStatus={setPhoto} onReview={() => open("review")} /></div>
        {panel === "settings" && <div className="cabin-settings workspace-page-surface"><h1 className="workspace-page-heading">Workspace settings</h1>
          <p>Expand an individual reading to see its history. Arrange cards changes only the capture and handoff layout; patient context, alerts and recording controls stay pinned. Browser zoom and pinch remain available. Phase buttons change this workspace only.</p>
          <div className="cabin-actions">{([1, 1.25, 1.5] as const).map((scale) => <button className="cabin-button" key={scale} aria-pressed={ui.typeScale === scale} onClick={() => setUi({ typeScale: scale })}>Text {scale * 100}%</button>)}</div>
          <details><summary><Info size={18} />What runs in the background?</summary><p>After you start listening, audio is captured continuously and sent in approximately 8-second clips to this vehicle’s server. Transcription and extraction may take longer. Speaker identity is not detected. Verify every ambient fact before it can contribute to scores or be shared.</p><p>The local viewfinder reads a frozen image after you tap Read photo. A separately connected camera can watch a selected region when auto capture is explicitly enabled. Scores use confirmed facts. Handoff delivery status is a server acknowledgment, not proof a clinician has read it.</p><p>Microphone pauses when the tab is hidden. Patient change, lost connection, or leaving this view stops capture. Unsent audio is not a durable backup.</p></details>
          <div className="cabin-actions"><button className="cabin-button" onClick={() => setUi({ presentationMode: true })}>Guided demo</button><button className="cabin-button" onClick={() => setUi({ mode: "explain" })}>Detailed application view</button>
            <button className="cabin-button" disabled={recording || ambient.status.queued > 0 || photo.busy} onClick={() => setUi({ confirmNewIncident: true })}>New incident…</button></div>
          <p className="cabin-muted">Prototype for demonstration. Not validated for use during patient care.</p>
        </div>}
      </section>
      <div hidden={!!panel} className="overview-grid"><WorkspaceCards cards={{
        capture: { label: "Capture & evidence", content: <>
          <div className="workspace-card-heading"><span className="workspace-icon"><Mic size={22} /></span><div><h3>Capture & evidence</h3><p>Words and images, ready for your review</p></div></div>
          <button className="capture-note-preview" onClick={() => open("notes")}><span className="cabin-eyebrow">{processing ? `${processing} notes processing` : errors ? `${errors} notes need attention` : "LATEST CAPTURE"}<ChevronRight size={18} /></span><p>{latest?.text ?? "Your next note starts here. Listen hands-free or type what you observe."}</p><small>{latest ? `Captured ${hhmm(latest.ts)} · expand transcript & evidence` : "Microphone stays off until you start"}</small></button>
          <div className="capture-visual-summary"><Camera size={20} /><div><strong>{photo.busy ? "Reading your photo…" : photo.failed ? "Photo needs attention" : "Visual evidence"}</strong><p>{photo.message || "Monitor, medication label, form or scene"}</p></div><button className="component-expand" aria-label="Open visual evidence" onClick={() => open("camera")}><ChevronRight size={20} /></button></div>
          <CaptureControl compact onSetup={() => open("camera")} />
        </> },
        handoff: { label: "Receiving team", content: <>
          <div className="workspace-card-heading"><span className="workspace-icon"><FileText size={22} /></span><div><h3>Receiving team</h3><p>The patient story, ready to share</p></div></div>
          <p className="handoff-destination">{destination?.status === "confirmed" ? String(destination.value) : "Destination not confirmed"}</p>
          <div className="handoff-summary"><span>{s?.relay.authorized ? "Sharing authorized" : "Sharing not authorized"}</span><strong>{s?.relay.authorized ? `${queuedCount(s)} fields queued` : "Confirmed facts stay on this vehicle"}</strong></div>
          <p className="workspace-caption">Receiving-system delivery is separate from a clinician reading the report.</p>
          <button className="cabin-button handoff-open" onClick={() => open("handoff")}><FileText size={19} />Open read-aloud handoff<ChevronRight size={18} /></button>
        </> },
      }} /><CareSummary onReview={() => open("review")} /></div>
    </main>
    <footer className="cabin-dock">
      <div className="cabin-listening-status"><span className={`cabin-mic-icon ${recording ? "active" : ""}`}>{recording ? <Mic size={23} /> : <MicOff size={23} />}</span>
        <div><strong>{ambient.status.listening ? "Microphone on · listening" : ambient.status.starting ? "Waiting for microphone" : "Microphone off"}</strong>
          <p role={ambient.status.error ? "alert" : "status"}>{ambient.status.queued ? `${ambient.status.queued} audio clip(s) processing · ` : ""}{ambient.status.message}</p>
          <meter min={0} max={1} value={ambient.status.level} aria-label="Microphone input level" />
          <span className="cabin-camera-status">{photo.active ? "This device: camera preview on · " : ""}{stale && !isReplay ? "Camera last known" : "Connected camera"}: {cameraState}{stale && !isReplay ? " · disconnected" : ""}{s?.capture?.pending ? ` · ${s.capture.pending} waiting` : ""}</span>
          {s?.capture?.error && <p role="alert">Camera capture needs attention: {s.capture.error}</p>}</div></div>
      <div className="cabin-actions">
        {s?.capture?.auto && <CaptureControl stopOnly />}
        {/* Start stays available while queued clips upload; it is disabled only when capture is blocked or alerts are held. */}
        <button className={`cabin-button ${recording ? "recording" : "primary"}`} disabled={ambient.blocked || (!recording && ui.heldAlerts)} onClick={() => recording ? ambient.pause() : void ambient.start()}>
          {recording ? <Pause size={23} /> : <Mic size={23} />}{recording ? "Pause listening" : "Start listening"}</button>
        {panel !== "camera" && <button className="cabin-button" onClick={() => open("camera")}><Camera size={23} />Camera</button>}
        <ManualEntry key={s?.incident.id} />
        {panel !== "camera" && <button className="cabin-button dock-type-note" onClick={() => open("notes")}><Keyboard size={19} />Type a note</button>}
      </div>
      <p className="cabin-dock-note">Record only when authorized · captured speech needs verification · {isReplay ? "demo replay" : stale ? "vehicle server disconnected" : "processed on the vehicle"}</p>
    </footer>
    <ProtocolSearch open={protocols} onClose={() => setProtocols(false)} />
  </div></div>;
}
