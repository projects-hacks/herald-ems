import { useEffect, useRef, useState } from "react";
import { Activity, ArrowLeft, BookOpen, Camera, ChevronRight, ClipboardCheck, FileText, Info, Maximize2, Mic, MicOff, Moon, Pause, Settings2, Sun, TriangleAlert, Users, X } from "lucide-react";
import { ManualEntry } from "@/components/ManualEntry";
import { PatientRoster } from "@/components/PatientRoster";
import { CompactStatus } from "@/components/CompactStatus";
import { CaptureControl } from "@/features/capture/CaptureControl";
import { CaptureBar } from "@/features/capture/CaptureBar";
import { ProtocolSearch } from "@/features/protocols/ProtocolSearch";
import { allFacts, queuedCount } from "@/lib/selectors";
import { ConnectBand, StaleOverlay } from "@/components/GlobalStates";
import { AttentionQueue } from "@/features/attention/AttentionQueue";
import { StatTiles } from "@/features/overview/StatTiles";
import { useAttention } from "@/hooks/useAttention";
import { useNow } from "@/hooks/useNow";
import { useContract } from "@/lib/contract";
import { clockSeconds, hhmm, hhmmss, shortId } from "@/lib/format";
import { useHerald, type IncidentPhase } from "@/lib/store";
import { PatientPage } from "@/pages/PatientPage";
import { TrendsPage } from "@/pages/TrendsPage";
import { TranscriptPage } from "@/pages/TranscriptPage";
import { HandoffPage } from "@/pages/HandoffPage";
import { CameraCapture, type CameraStatus } from "./CameraCapture";
import { useAmbient } from "./useAmbient";
import "./cabin.css";

type Panel = "review" | "patient" | "trends" | "notes" | "handoff" | "camera" | "settings" | null;
const TITLES = { review: "Review captured information", patient: "Patient record & sources", trends: "Readings, trends & scores", notes: "Captured notes & processing", handoff: "Receiving-team handoff", camera: "Capture visual evidence", settings: "Workspace settings" };
const VITALS = ["vitals.hr", "vitals.sbp", "vitals.spo2", "vitals.rr"];

export function CabinApp() {
  const s = useHerald((st) => st.snapshot);
  const ui = useHerald((st) => st.ui);
  const source = useHerald((st) => st.source);
  const stale = useHerald((st) => st.stale || st.conn !== "open");
  const at = useHerald((st) => st.lastStateAt);
  const health = useHerald((st) => st.health);
  const setUi = useHerald((st) => st.setUi);
  const a = useAttention();
  const contract = useContract();
  const now = useNow();
  const ambient = useAmbient();
  const [panel, setPanel] = useState<Panel>(null);
  const [focus, setFocus] = useState(false);
  const [protocols, setProtocols] = useState(false);
  const [photo, setPhoto] = useState<CameraStatus>({ busy: false, message: "", failed: false });
  const heading = useRef<HTMLHeadingElement>(null);
  const lastTrigger = useRef<HTMLElement | null>(null);
  const open = (value: Panel) => { lastTrigger.current = document.activeElement as HTMLElement; setPanel(value); };
  const close = () => { setPanel(null); requestAnimationFrame(() => lastTrigger.current?.focus()); };
  useEffect(() => { if (panel) heading.current?.focus({ preventScroll: true }); }, [panel]);
  useEffect(() => { setPanel(null); }, [s?.incident.id]);
  useEffect(() => { if (ui.page !== "overview") { setPanel(ui.page === "transcript" ? "notes" : ui.page); setUi({ page: "overview" }); } }, [ui.page, setUi]);
  const recording = ambient.status.listening || ambient.status.starting;
  const elapsed = s?.clocks.find((c) => c.id === "scene");
  const identity = s?.facts["patient.name"];
  const destination = s?.facts["transport.destination"];
  const latest = s?.transcripts.at(-1);
  const proposed = s ? allFacts(s).filter((f) => f.status === "unconfirmed").length : 0;
  const processing = s?.transcripts.filter((t) => t.trace.model.status === "running").length ?? 0;
  const errors = s?.transcripts.filter((t) => t.trace.model.status === "error").length ?? 0;
  const headline = a?.urgent[0]?.label ?? a?.choose[0]?.label ?? a?.confirmAlerts[0]?.label ?? a?.review[0]?.label;
  const isReplay = source === "fixture";
  return <div className={`cabin ${focus ? "cabin-focus" : ""}`}>
    <header className="cabin-header">
      <div className="cabin-brand"><Activity size={25} aria-hidden /><span>HERALD<small>AMBULANCE WORKSPACE</small></span></div>
      <div className="cabin-phase" role="group" aria-label="Workspace phase, this screen only">
        {(["scene", "transport", "handoff"] as IncidentPhase[]).map((phase) => <button key={phase} aria-pressed={ui.incidentPhase === phase}
          onClick={() => { setUi({ incidentPhase: phase }); if (phase === "handoff") open("handoff"); }}>{phase}</button>)}
      </div>
      <div className="cabin-header-actions">
        <button className="cabin-button" onClick={() => setProtocols(true)}><BookOpen size={20} />Protocols</button>
        <button className="cabin-button" aria-pressed={focus} onClick={() => setFocus(!focus)}><Maximize2 size={20} />{focus ? "Standard view" : "Large view"}</button>
        <button className="cabin-button" aria-label={ui.theme === "dark" ? "Use daylight theme" : "Use night theme"} onClick={() => setUi({ theme: ui.theme === "dark" ? "light" : "dark" })}>{ui.theme === "dark" ? <Sun size={21} /> : <Moon size={21} />}</button>
        <button className="cabin-button" aria-label="Workspace settings" onClick={() => open("settings")}><Settings2 size={21} /></button>
      </div>
    </header>
    <PatientRoster />
    <CompactStatus always />
    <CaptureControl />
    <div className="cabin-sticky-status">
      <div className="cabin-patient-context"><span>{identity?.status === "confirmed" ? String(identity.value) : "Patient identity not confirmed"} · incident {s ? shortId(s.incident.id) : "not loaded"}</span><span>{destination?.status === "confirmed" ? String(destination.value) : "Destination not confirmed"}</span></div>
      <ConnectBand /><StaleOverlay />
      {isReplay && <p className="cabin-replay">REPLAY · recorded scenario, not a live patient · capture disabled</p>}
      <button id="cabin-attention" className={`cabin-attention ${a?.urgent.length ? "urgent" : ""}`} onClick={() => open("review")}>
        <TriangleAlert size={23} aria-hidden />
        <span><strong>{headline ?? (proposed ? `${proposed} captured facts need verification` : "No open review items")}</strong>
          <small>{a?.urgent.length ? `${a.urgent.length} high-priority finding(s) · open review` : headline ? "Open review for evidence and details" : "Missing information is not a normal finding"}</small></span>
        <span className="cabin-count">{a?.count ?? 0}<small>to review</small></span><ChevronRight size={23} aria-hidden />
      </button>
      <span className="sr-only" role="alert">{a?.urgent.map((alert) => alert.label).join(". ")}</span>
    </div>
    <main className="cabin-main">
      <section className="cabin-patient" aria-label="Current patient">
        <div><p className="cabin-eyebrow">CURRENT PATIENT <span>{s ? shortId(s.incident.id) : "Connecting…"}</span></p>
          <h1>{identity?.status === "confirmed" ? String(identity.value) : "Identity not confirmed"}</h1>
          <p>{s?.summary || "Start capture or enter a patient fact"}</p>
          <p className="cabin-muted">{s?.facts["patient.identifier"]?.status === "confirmed" ? `ID ${s.facts["patient.identifier"].value}` : "Patient identifier not confirmed"}{s?.incident.dispatch ? ` · Dispatch ${s.incident.dispatch}` : ""}</p>
        </div>
        <div className="cabin-journey"><span>CALL ELAPSED</span><strong>{elapsed ? hhmmss(clockSeconds(elapsed, at, now)) : "—"}</strong>
          <p>{destination?.status === "confirmed" ? String(destination.value) : "Destination not confirmed"}</p></div>
      </section>
      <div className="cabin-section-label"><h2>Latest documented readings</h2><span>Not a live monitor feed · tap for history</span></div>
      <section className="cabin-vitals" aria-label="Latest documented readings">
        {VITALS.map((key) => {
          const fact = s?.facts[key];
          const confirmed = fact?.status === "confirmed" && fact.value !== null;
          const label = contract?.keys[key]?.label ?? key.split(".").at(-1)?.toUpperCase();
          return <button key={key} className={`cabin-vital ${!confirmed ? "unknown" : ""}`} onClick={() => open(confirmed ? "trends" : "review")}>
            <span className="cabin-vital-label">{label}<ChevronRight size={18} aria-hidden /></span>
            <span className="cabin-vital-value">{confirmed ? String(fact.value) : "—"}<small>{fact?.unit ?? contract?.keys[key]?.unit}</small></span>
            <span className="cabin-vital-meta">{fact ? `${confirmed ? "Confirmed" : "Needs verification"} · recorded ${hhmm(fact.ts)}` : "Not captured"}{stale && !isReplay ? " · disconnected" : ""}</span>
          </button>;
        })}
      </section>
      <nav className="cabin-workspaces" aria-label="Patient workspace">
        <button aria-pressed={panel === "review"} onClick={() => open("review")}><ClipboardCheck size={22} /><span>Review<small>{proposed} unverified facts</small></span></button>
        <button aria-pressed={panel === "patient"} onClick={() => open("patient")}><Users size={22} /><span>Patient<small>History & evidence</small></span></button>
        <button aria-pressed={panel === "trends"} onClick={() => open("trends")}><Activity size={22} /><span>Trends<small>Readings & scores</small></span></button>
        <button aria-pressed={panel === "handoff"} onClick={() => open("handoff")}><FileText size={22} /><span>Handoff<small>{s?.relay.authorized ? `${queuedCount(s)} fields queued · link ${s.relay.link}` : "Sharing not authorized"}</small></span></button>
      </nav>
      {panel ? <section className="cabin-detail" aria-label={TITLES[panel]} onKeyDown={(e) => { if (e.key === "Escape" && e.target === heading.current) close(); }}>
        <div className="cabin-detail-header"><h2 ref={heading} tabIndex={-1}>{TITLES[panel]}</h2><button className="cabin-button" onClick={close}><X size={20} />Close details</button></div>
        {panel === "review" && <AttentionQueue />}
        {panel === "patient" && <PatientPage />}
        {panel === "trends" && <><StatTiles /><TrendsPage /></>}
        {panel === "notes" && <><TranscriptPage /><CaptureBar allowVoice={!recording && ambient.status.queued === 0} /></>}
        {panel === "handoff" && <HandoffPage />}
        {panel === "settings" && <div className="cabin-settings">
          <p>Layout stays fixed during care. Use Large view or text size controls; browser zoom and pinch remain available. Phase buttons change this workspace only.</p>
          <div className="cabin-actions">{([1, 1.25, 1.5] as const).map((scale) => <button className="cabin-button" key={scale} aria-pressed={ui.typeScale === scale} onClick={() => setUi({ typeScale: scale })}>Text {scale * 100}%</button>)}</div>
          <details><summary><Info size={18} />What runs in the background?</summary><p>After you start listening, audio is captured continuously and sent in approximately 8-second clips to this vehicle’s server. Transcription and extraction may take longer. Speaker identity is not detected. Verify every ambient fact before it can contribute to scores or be shared.</p><p>The camera reads a frozen image only after you tap Read this image. Scores use confirmed facts. Handoff delivery status is a server acknowledgment, not proof a clinician has read it.</p><p>Microphone pauses when the tab is hidden. Patient change, lost connection, or leaving this view stops capture. Unsent audio is not a durable backup.</p></details>
          <div className="cabin-actions"><button className="cabin-button" onClick={() => setUi({ presentationMode: true })}>Guided demo</button><button className="cabin-button" onClick={() => setUi({ mode: "explain" })}>Detailed application view</button>
            <button className="cabin-button" disabled={recording || ambient.status.queued > 0 || photo.busy} onClick={() => setUi({ confirmNewIncident: true })}>New incident…</button></div>
          <p className="cabin-muted">Prototype for demonstration. Not validated for use during patient care.</p>
        </div>}
      </section> : <section className="cabin-background" aria-label="Background work">
        <button className="cabin-background-card" onClick={() => open("notes")}><span className="cabin-eyebrow"><Mic size={18} />CAPTURED NOTES <ChevronRight size={18} /></span>
          <strong>{processing ? `${processing} extraction${processing === 1 ? "" : "s"} processing` : errors ? `${errors} processing error${errors === 1 ? "" : "s"} in recent notes` : latest ? "Latest captured words" : "Ready when you are"}</strong>
          <p>{latest?.text ?? "Start listening once, then keep your hands on care. Captured words and their sources will appear here."}</p>
          <small>{latest ? `Captured ${hhmm(latest.ts)} · tap for the full record` : "No audio is recorded until you start"}</small></button>
        <button className="cabin-background-card" onClick={() => open("camera")}><span className="cabin-eyebrow"><Camera size={18} />VISUAL EVIDENCE <ChevronRight size={18} /></span>
          <strong>{photo.busy ? "Reading your photo locally…" : photo.failed ? "Photo needs attention" : "Point. Freeze. Verify."}</strong><p>{photo.message || "Read a monitor, medication label, document, or scene photo without retyping it."}</p><small>Camera off · opens only when requested</small></button>
      </section>}
      <div hidden={panel !== "camera"}><CameraCapture key={s?.incident.id} visible={panel === "camera"} onStatus={setPhoto} /></div>
    </main>
    <footer className="cabin-dock">
      <div className="cabin-listening-status"><span className={`cabin-mic-icon ${recording ? "active" : ""}`}>{recording ? <Mic size={23} /> : <MicOff size={23} />}</span>
        <div><strong>{ambient.status.listening ? "Microphone on · listening" : ambient.status.starting ? "Waiting for microphone" : "Microphone off"}</strong>
          <p role={ambient.status.error ? "alert" : "status"}>{ambient.status.queued ? `${ambient.status.queued} audio clip(s) processing · ` : ""}{ambient.status.message}</p>
          <meter min={0} max={1} value={ambient.status.level} aria-label="Microphone input level" /></div></div>
      <div className="cabin-actions">
        <button className={`cabin-button ${recording ? "recording" : "primary"}`} disabled={ambient.blocked || (!recording && (ambient.status.queued > 0 || ui.heldAlerts))} onClick={() => recording ? ambient.pause() : void ambient.start()}>
          {recording ? <Pause size={23} /> : <Mic size={23} />}{recording ? "Pause listening" : "Start listening"}</button>
        <button className="cabin-button" disabled={ambient.blocked} onClick={() => open("camera")}><Camera size={23} />Camera</button>
        <ManualEntry key={s?.incident.id} />
        <button className="cabin-button" onClick={() => open("notes")}>Type a note</button>
        {panel && <button className="cabin-button" onClick={close}><ArrowLeft size={20} />Overview</button>}
      </div>
      <p className="cabin-dock-note">Start only when recording is authorized · ambient speakers unverified · {health?.stt_loaded ? "local speech model loaded" : "local speech model may need to warm up"} · {isReplay ? "replay" : stale ? "server disconnected" : "vehicle server connected"}</p>
    </footer>
    <ProtocolSearch open={protocols} onClose={() => setProtocols(false)} />
  </div>;
}
