// The sidebar, in the iPad Health / Settings style: the app title, the pages as rows with colored icon tiles and
// counts, the replay controls (fixture mode), "On this vehicle" as an inset grouped list, and the screen settings.
// Collapses to an icon rail (the medic's choice, remembered; explain mode forces the rail so the trace has room).
// Below 1024 px it becomes a top bar with the pages in a row.
import {
  AudioLines, Cpu, HeartPulse, LayoutGrid, Mic, Moon, PanelLeftClose, PanelLeftOpen, Pause, Play, RotateCcw, Send,
  ShieldCheck, SkipForward, Sparkles, Sun, Type, UserRound, Wifi, type LucideIcon,
} from "lucide-react";
import { useAttention } from "@/hooks/useAttention";
import { useContract } from "@/lib/contract";
import { erRows, queuedCount } from "@/lib/selectors";
import { useHerald, type Page, type TypeScale } from "@/lib/store";
import type { LinkState } from "@/lib/types";
import { cn } from "@/lib/utils";
import type { FixturePlayer } from "@/lib/ws";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Dot, IconTile, type Cat, type Tone } from "@/components/kit";

const NEXT_SCALE: Record<number, TypeScale> = { 1: 1.25, 1.25: 1.5, 1.5: 1 };

function Tip({ show, label, children }: { show: boolean; label: string; children: React.ReactElement }) {
  if (!show) return children;
  return <Tooltip><TooltipTrigger asChild>{children}</TooltipTrigger><TooltipContent side="right">{label}</TooltipContent></Tooltip>;
}

function NavItem({ page, icon, cat, label, count, urgent, rail }: {
  page: Page; icon: LucideIcon; cat: Cat; label: string; count?: number; urgent?: boolean; rail: boolean;
}) {
  const active = useHerald((s) => s.ui.page === page);
  const setUi = useHerald((s) => s.setUi);
  const n = count || undefined;
  return (
    <Tip show={rail} label={n ? `${label} · ${n}` : label}>
      <button type="button" onClick={() => setUi({ page })} aria-current={active ? "page" : undefined} aria-label={rail ? label : undefined}
        className={cn("relative flex h-12 w-full items-center gap-3 rounded-[12px] text-[1.0625rem] font-medium transition-colors duration-[var(--dur-short3)]",
          rail ? "justify-center px-0" : "pr-3 pl-2",
          active ? "bg-accent-fill text-on-accent-fill" : "text-text-primary hover:bg-surface-2",
          "max-lg:h-11 max-lg:w-auto max-lg:shrink-0 max-lg:px-2")}>
        <IconTile icon={icon} cat={cat} size={30} />
        <span className={cn("truncate", rail && "lg:sr-only")}>{label}</span>
        {n !== undefined && (rail
          ? <span className={cn("num absolute top-0.5 right-1.5 grid min-w-5 place-items-center rounded-full px-1 text-[0.6875rem] leading-5 font-bold",
              urgent ? "bg-high-fill text-high-on-fill" : "bg-surface-3 text-text-primary")}>{n}</span>
          : urgent
            ? <span className="num ml-auto grid min-w-6 place-items-center rounded-full bg-high-fill px-1.5 text-meta leading-5 font-bold text-high-on-fill max-lg:ml-0">{n}</span>
            : <span className={cn("num ml-auto text-body max-lg:ml-0", active ? "text-on-accent-fill/85" : "text-text-muted")}>{n}</span>)}
      </button>
    </Tip>
  );
}

function CaptureNav({ rail }: { rail: boolean }) {
  const focusCapture = () => {
    document.getElementById("capture-dock")?.scrollIntoView({ behavior: "smooth", block: "end" });
    requestAnimationFrame(() => (document.querySelector('#capture-dock button[aria-label*="record the medic"]') as HTMLButtonElement | null)?.focus());
  };
  return (
    <Tip show={rail} label="Capture patient information">
      <button type="button" onClick={focusCapture} aria-label={rail ? "Capture" : undefined}
        className={cn("flex h-12 w-full items-center gap-3 rounded-[12px] text-[1.0625rem] font-medium text-text-primary hover:bg-surface-2",
          rail ? "justify-center px-0" : "pr-3 pl-2", "max-lg:h-11 max-lg:w-auto max-lg:shrink-0 max-lg:px-2")}>
        <IconTile icon={Mic} cat="speech" size={30} /><span className={cn("truncate", rail && "lg:sr-only")}>Capture</span>
      </button>
    </Tip>
  );
}

function StatusRow({ icon: Icon, label, value, tone, rail }: { icon: LucideIcon; label: string; value: string; tone: Tone; rail: boolean }) {
  if (rail) {
    return (
      <Tip show label={`${label}: ${value}`}>
        <span className="relative grid size-10 place-items-center rounded-[10px] text-text-muted" role="img" aria-label={`${label}: ${value}`} tabIndex={0}>
          <Icon size={18} aria-hidden /><Dot tone={tone} className="absolute top-1.5 right-1.5 ring-2 ring-surface-1" />
        </span>
      </Tip>
    );
  }
  return (
    <div className="flex min-h-10 items-center gap-2.5 border-b border-border-subtle px-3 last:border-0">
      <Icon size={16} aria-hidden className="shrink-0 text-text-muted" />
      <span className="shrink-0 text-meta text-text-secondary">{label}</span>
      <span className="ml-auto flex min-w-0 items-center gap-1.5 text-meta font-semibold text-text-primary" title={value}>
        <Dot tone={tone} /><span className="truncate">{value}</span>
      </span>
    </div>
  );
}

function linkStatus(link: LinkState, configured: boolean, emulated: boolean): [Tone, string] {
  if (!configured) return ["neutral", "not set up"];
  const e = emulated ? " (emulated)" : "";
  return link === "good" ? ["ok", `good${e}`] : link === "weak" ? ["low", `weak${e}`] : link === "down" ? ["low", `offline${e}`] : ["low", "checking…"];
}

function VehicleStatus({ rail }: { rail: boolean }) {
  const s = useHerald((st) => st.snapshot);
  const health = useHerald((st) => st.health);
  const source = useHerald((st) => st.source);
  const explain = useHerald((st) => st.ui.mode === "explain");
  const lastModel = s?.transcripts.findLast((t) => ["done", "error"].includes(t.trace.model.status))?.trace.model;
  const replay = source === "fixture";
  const model = replay ? lastModel?.name ?? null : health?.llm_model ?? null;
  const [speechTone, speech]: [Tone, string] = replay ? ["neutral", "replay"] : health?.stt_loaded ? ["ok", "speech ready"] : ["low", health ? "speech warming" : "checking"];
  const [modelTone, modelText]: [Tone, string] = lastModel?.status === "error" ? ["low", "error · rules only"]
    : model ? ["ok", model] : replay ? ["neutral", "replay"] : ["low", health ? "off · rules only" : "—"];
  const [linkTone, linkText] = s ? linkStatus(s.relay.link, s.relay.configured, !!s.netem) : (["neutral", "—"] as [Tone, string]);
  const cloud = s?.counters.cloud_ai_calls;
  const rows = <>
    <StatusRow rail={rail} icon={Mic} label="Capture" value={speech} tone={speechTone} />
    <StatusRow rail={rail} icon={Wifi} label="ED link" value={linkText} tone={linkTone} />
    {explain && <StatusRow rail={rail} icon={Cpu} label="Local model" value={modelText} tone={modelTone} />}
    {explain && <StatusRow rail={rail} icon={ShieldCheck} label="Cloud AI" value={cloud === undefined ? "—" : `${cloud} calls`} tone={cloud ? "high" : "ok"} />}
  </>;
  if (rail) return <div className="flex flex-col items-center gap-1" role="group" aria-label="System status">{rows}</div>;
  return (
    <div className="flex flex-col gap-1.5" role="group" aria-label="System status">
      <p className="label-caps px-3 text-text-muted">System status</p>
      <div className="rounded-[12px] bg-surface-2">{rows}</div>
    </div>
  );
}

function ReplayCard({ player, rail }: { player: FixturePlayer; rail: boolean }) {
  const f = useHerald((s) => s.fixture);
  if (!f) return null;
  const toggle = () => (f.playing ? player.pause() : player.play());
  const btn = "hit grid size-9 place-items-center rounded-full text-herald-accent hover:bg-accent-tint";
  if (rail) {
    return (
      <Tip show label={`Replay ${f.index} / ${f.total} · not live`}>
        <button type="button" onClick={toggle} aria-label={f.playing ? "Pause replay" : "Play replay"}
          className="grid size-12 place-items-center rounded-full bg-accent-tint text-herald-accent">
          {f.playing ? <Pause size={18} fill="currentColor" /> : <Play size={18} fill="currentColor" />}
        </button>
      </Tip>
    );
  }
  return (
    <div className="flex flex-col gap-2 rounded-[14px] bg-surface-2 p-3" role="status" aria-label="Replay controls">
      <div className="flex items-center gap-2 text-meta">
        <span className="rounded-[5px] bg-accent-fill px-1.5 py-px text-[0.6875rem] font-bold tracking-wide text-on-accent-fill">REPLAY</span>
        <span className="truncate font-semibold text-text-primary" title={`${f.name} · not live · actions are off`}>{f.name}</span>
        <span className="num ml-auto shrink-0 text-text-muted">{f.index}/{f.total}</span>
      </div>
      <span className="block h-1 overflow-hidden rounded-full bg-surface-3" aria-hidden>
        <span className="block h-full rounded-full bg-herald-accent" style={{ width: `${(f.index / Math.max(f.total, 1)) * 100}%` }} />
      </span>
      <div className="flex items-center gap-1">
        <button type="button" className={btn} onClick={() => player.restart()} aria-label="Restart replay"><RotateCcw size={16} /></button>
        <button type="button" className={cn(btn, "size-10 bg-accent-fill text-on-accent-fill hover:bg-accent-fill hover:brightness-110")} onClick={toggle} aria-label={f.playing ? "Pause replay" : "Play replay"}>
          {f.playing ? <Pause size={16} fill="currentColor" /> : <Play size={16} fill="currentColor" className="translate-x-px" />}
        </button>
        <button type="button" className={btn} onClick={() => player.step()} aria-label="Next recorded message"><SkipForward size={16} /></button>
        <select aria-label="Replay speed" value={f.speed} onChange={(e) => player.setSpeed(Number(e.target.value))}
          className="ml-auto h-9 rounded-[9px] bg-transparent px-1 text-meta font-semibold text-herald-accent hover:bg-accent-tint">
          {[1, 2, 4].map((sp) => <option key={sp} value={sp}>{sp}×</option>)}
        </select>
      </div>
    </div>
  );
}

function Settings({ rail, narrow = false }: { rail: boolean; narrow?: boolean }) {
  const ui = useHerald((s) => s.ui);
  const setUi = useHerald((s) => s.setUi);
  const btn = "hit grid size-10 place-items-center rounded-full text-text-muted hover:bg-surface-2 hover:text-text-primary";
  const explain = ui.mode === "explain";
  return (
    <div className={cn("flex items-center gap-1", rail ? "flex-col" : "px-1")}>
      <Tip show label={ui.theme === "dark" ? "Light appearance (Shift+L)" : "Dark appearance (Shift+L)"}>
        <button type="button" className={btn} onClick={() => setUi({ theme: ui.theme === "dark" ? "light" : "dark" })} aria-label="Switch appearance">
          {ui.theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
        </button>
      </Tip>
      <Tip show label={`Text size ${ui.typeScale}× (Shift+T)`}>
        <button type="button" className={btn} onClick={() => setUi({ typeScale: NEXT_SCALE[ui.typeScale] })} aria-label={`Text size ${ui.typeScale}×`}><Type size={18} /></button>
      </Tip>
      <Tip show label={explain ? "Back to the medic view (Shift+E)" : "Explain: show what Herald heard and did (Shift+E)"}>
        <button type="button" className={cn(btn, explain && "bg-accent-tint text-herald-accent")} aria-pressed={explain}
          onClick={() => setUi({ mode: explain ? "medic" : "explain" })} aria-label="Explain mode"><Sparkles size={18} /></button>
      </Tip>
      {!explain && !narrow && (
        <Tip show label={ui.sidebarCollapsed ? "Show the sidebar" : "Hide the sidebar"}>
          <button type="button" className={cn(btn, !rail && "ml-auto")} onClick={() => setUi({ sidebarCollapsed: !ui.sidebarCollapsed })}
            aria-label={ui.sidebarCollapsed ? "Show the sidebar" : "Hide the sidebar"}>
            {ui.sidebarCollapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          </button>
        </Tip>
      )}
    </div>
  );
}

export function Sidebar({ player }: { player: FixturePlayer | null }) {
  const s = useHerald((st) => st.snapshot);
  const rail = useHerald((st) => st.ui.sidebarCollapsed || st.ui.mode === "explain");
  const a = useAttention();
  const c = useContract();
  const held = s && s.relay.authorized ? erRows(s, c).filter((r) => r.state === "held").length : 0;
  const queued = s ? queuedCount(s) : 0;
  const significant = s ? s.changed.filter((t) => t.significant).length : 0;
  return (
    <aside aria-label="Herald" className={cn("flex shrink-0 flex-col gap-5 overflow-y-auto border-r border-border-subtle bg-surface-1 py-5 transition-[width] duration-[var(--dur-short4)]",
      rail ? "w-[var(--sidebar-rail-w)] items-center px-3" : "w-[var(--sidebar-w)] px-3",
      "max-lg:w-full max-lg:flex-row max-lg:items-center max-lg:gap-3 max-lg:border-r-0 max-lg:border-b max-lg:px-4 max-lg:py-2")}>
      {rail
        ? <span className="grid size-10 place-items-center rounded-[11px] text-white" style={{ backgroundImage: "linear-gradient(160deg, #FF5A78, #FF2D55 55%, #D70015)" }} aria-label="Herald"><AudioLines size={20} strokeWidth={2.4} /></span>
        : <div className="px-2 max-lg:hidden">
            <p className="text-large-title font-bold tracking-display">Herald</p>
            <p className="text-meta text-text-muted">NOW · on this vehicle</p>
          </div>}
      <nav aria-label="Workflow" className={cn("flex w-full flex-col gap-0.5", "max-lg:flex-row max-lg:overflow-x-auto")}>
        <NavItem rail={rail} page="overview" icon={LayoutGrid} cat="attention" label="Now" count={a?.count} urgent={!!a?.urgent.length} />
        <CaptureNav rail={rail} />
        <NavItem rail={rail} page="handoff" icon={Send} cat="ed" label="Handoff" count={held || queued} />
        {!rail && <p className="label-caps mt-3 px-3 text-text-muted max-lg:hidden">Clinical record</p>}
        <NavItem rail={rail} page="patient" icon={UserRound} cat="patient" label="Patient" />
        <NavItem rail={rail} page="trends" icon={HeartPulse} cat="heart" label="Vitals" count={significant} />
        <NavItem rail={rail} page="transcript" icon={AudioLines} cat="speech" label="Audit" />
      </nav>
      <div className="flex-1 max-lg:hidden" />
      {!rail && <button type="button" className="min-h-12 rounded-xl bg-surface-2 px-3 text-body font-semibold max-lg:hidden"
        onClick={() => useHerald.getState().setUi({ confirmNewIncident: true })}>New patient / incident</button>}
      <div className="flex w-full flex-col gap-4 max-lg:hidden">
        {player && <ReplayCard player={player} rail={rail} />}
        <VehicleStatus rail={rail} />
        <Settings rail={rail} />
      </div>
      <div className="ml-auto hidden items-center gap-1 max-lg:flex">
        {player && <ReplayCard player={player} rail />}
        <Settings rail={false} narrow />
      </div>
    </aside>
  );
}
