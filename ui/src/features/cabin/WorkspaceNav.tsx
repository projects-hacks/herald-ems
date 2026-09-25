import { Activity, ArrowUpRight, AudioLines, BookOpen, Camera, ChartNoAxesCombined, FileText, LayoutDashboard, LockKeyhole, Settings2, ShieldCheck, UserRound, type LucideIcon } from "lucide-react";
import { useHerald } from "@/lib/store";
import type { FixturePlayer } from "@/lib/ws";
import { Pause, Play, RotateCcw, SkipForward } from "lucide-react";

export type WorkspacePanel = "review" | "patient" | "patients" | "trends" | "notes" | "handoff" | "camera" | "settings" | "protocols" | null;
const ITEMS: { panel: WorkspacePanel; label: string; short: string; icon: LucideIcon }[] = [
  { panel: null, label: "Now", short: "Now", icon: LayoutDashboard },
  { panel: "patient", label: "Patient record", short: "Record", icon: UserRound },
  { panel: "trends", label: "Trends & scores", short: "Trends", icon: ChartNoAxesCombined },
  { panel: "notes", label: "Transcript & notes", short: "Notes", icon: AudioLines },
  { panel: "handoff", label: "ED handoff", short: "Handoff", icon: FileText },
  { panel: "camera", label: "Camera & monitor watch", short: "Camera", icon: Camera },
  { panel: "protocols", label: "Protocol library", short: "Protocols", icon: BookOpen },
];

export function WorkspaceNav({ panel, onOpen, count, player }: { panel: WorkspacePanel; onOpen: (panel: WorkspacePanel) => void; count: number; player?: FixturePlayer | null }) {
  const snapshot = useHerald((s) => s.snapshot);
  const health = useHerald((s) => s.health);
  const fixture = useHerald((s) => s.fixture);
  const replay = useHerald((s) => s.source === "fixture");
  const disconnected = useHerald((s) => s.stale || s.conn !== "open");
  const incidentActive = useHerald((s) => !!s.snapshot && !s.snapshot.incident.ended_at);
  return <aside className="workspace-sidebar" aria-label="Herald workspace">
    <a className="workspace-logo" aria-label="Herald overview" href="#workspace-main" onClick={(event) => { event.preventDefault(); onOpen(null); }}>
      <span className="workspace-logo-mark"><Activity size={26} strokeWidth={2.4} /></span>
      <span>herald<span className="workspace-logo-dot">.</span><small>CARE IN THE MOMENT</small></span>
    </a>
    {!incidentActive && <div className="workspace-team"><span className="workspace-team-icon"><ShieldCheck size={21} /></span><span>Medic workspace<small>{snapshot?.county.name || "On-board care team"}</small></span></div>}
    <p className="workspace-nav-label">PATIENT CARE</p>
    <nav aria-label="Care workspace" className="workspace-nav">
      {ITEMS.map(({ panel: value, label, short, icon: Icon }) => <button key={label} type="button" aria-label={label} title={label} aria-current={panel === value ? "page" : undefined} onClick={() => onOpen(value)}>
        <Icon size={20} strokeWidth={1.8} /><span>{label}</span><small className="workspace-nav-short">{short}</small>{value === null && count > 0 && <span className="workspace-nav-count">{count}</span>}
      </button>)}
    </nav>
    <div className="workspace-sidebar-bottom">
      {replay && player && fixture && <div className="workspace-replay"><span>RECORDED SCENARIO <small>{fixture.index}/{fixture.total}</small></span>
        <div><button onClick={() => fixture.playing ? player.pause() : player.play()} aria-label={fixture.playing ? "Pause replay" : "Play replay"}>{fixture.playing ? <Pause size={18} /> : <Play size={18} />}</button>
          <button onClick={() => player.step()} aria-label="Next recorded message"><SkipForward size={18} /></button>
          <button onClick={() => player.restart()} aria-label="Restart replay"><RotateCcw size={18} /></button></div>
      </div>}
      {!incidentActive && <div className="workspace-local"><span className="workspace-local-icon"><LockKeyhole size={18} /></span><strong>Built for the field</strong><p>Speech and images are processed on this vehicle.</p>
        <span className="workspace-engine-status">{replay ? "Recorded demo" : disconnected ? "Vehicle disconnected" : health?.llm_available === false ? "Extraction unavailable" : health?.llm_available ? "Local extraction ready" : "Checking local extraction"}</span>
      </div>}
      <button className="workspace-settings" aria-current={panel === "settings" ? "page" : undefined} onClick={() => onOpen("settings")}><Settings2 size={19} />Settings & display<ArrowUpRight size={16} /></button>
      {!incidentActive && <div className="workspace-edition"><span className="workspace-avatar"><UserRound size={18} /></span><span>On-board care<small>Herald EMS · Prototype</small></span></div>}
    </div>
  </aside>;
}
