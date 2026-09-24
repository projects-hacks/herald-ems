// The sidebar: the Herald mark, the pages, the replay controls (fixture mode), what is running on this vehicle, and
// the screen settings. Collapses to an icon rail (the medic's choice, remembered; explain mode forces the rail so the
// trace has room). Below 1024 px it becomes a top bar with the pages in a row.
import {
  Activity, ChartLine, Cpu, LayoutDashboard, Mic, Moon, PanelLeftClose, PanelLeftOpen, Pause, Play, RotateCcw, Send,
  ShieldCheck, SkipForward, Sparkles, Sun, Type, UserRound, AudioLines, type LucideIcon,
} from "lucide-react";
import { useAttention } from "@/hooks/useAttention";
import { erRows, queuedCount } from "@/lib/selectors";
import { useContract } from "@/lib/contract";
import { useHerald, type Page, type TypeScale } from "@/lib/store";
import type { LinkState } from "@/lib/types";
import { cn } from "@/lib/utils";
import type { FixturePlayer } from "@/lib/ws";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Count, Dot, type Tone } from "@/components/kit";

const NEXT_SCALE: Record<number, TypeScale> = { 1: 1.25, 1.25: 1.5, 1.5: 1 };

function Tip({ show, label, children }: { show: boolean; label: string; children: React.ReactElement }) {
  if (!show) return children;
  return <Tooltip><TooltipTrigger asChild>{children}</TooltipTrigger><TooltipContent side="right">{label}</TooltipContent></Tooltip>;
}

function NavItem({ page, icon: Icon, label, badge, tone = "neutral", rail }: {
  page: Page; icon: LucideIcon; label: string; badge?: number; tone?: Tone; rail: boolean;
}) {
  const active = useHerald((s) => s.ui.page === page);
  const setUi = useHerald((s) => s.setUi);
  return (
    <Tip show={rail} label={badge ? `${label} · ${badge}` : label}>
      <button type="button" onClick={() => setUi({ page })} aria-current={active ? "page" : undefined} aria-label={rail ? label : undefined}
        className={cn("relative flex h-12 w-full items-center gap-3 rounded-[12px] text-body font-medium transition-colors duration-[var(--dur-short3)]",
          rail ? "justify-center px-0" : "px-3",
          active ? "bg-surface-1 text-text-primary shadow-[var(--shadow-2)] ring-1 ring-border-subtle" : "text-text-secondary hover:bg-surface-1/60 hover:text-text-primary",
          "max-lg:h-11 max-lg:w-auto max-lg:shrink-0 max-lg:px-3")}>
        <Icon size={20} strokeWidth={2} aria-hidden className={cn("shrink-0", active && "text-herald-accent")} />
        {!rail && <span className="truncate max-lg:hidden">{label}</span>}
        {badge ? (rail
          ? <Count n={badge} tone={tone} className="absolute top-1 right-2 min-w-5 px-1 text-[0.6875rem] leading-4" />
          : <Count n={badge} tone={tone} className="ml-auto max-lg:ml-0" />) : null}
      </button>
    </Tip>
  );
}

function StatusRow({ icon: Icon, label, value, tone, rail }: { icon: LucideIcon; label: string; value: string; tone: Tone; rail: boolean }) {
  const body = rail ? (
    <span className="relative grid size-9 place-items-center rounded-[10px] text-text-muted">
      <Icon size={18} aria-hidden /><Dot tone={tone} className="absolute top-1.5 right-1.5 ring-2 ring-bg" />
    </span>
  ) : (
    <>
      <Icon size={16} aria-hidden className="shrink-0 text-text-muted" />
      <span className="shrink-0 text-meta text-text-muted">{label}</span>
      <span className="ml-auto flex min-w-0 items-center gap-1.5 text-meta font-semibold text-text-secondary" title={value}>
        <Dot tone={tone} /><span className="truncate">{value}</span>
      </span>
    </>
  );
  return (
    <Tip show={rail} label={`${label}: ${value}`}>
      <div className={cn("flex w-full items-center gap-2.5", rail ? "justify-center" : "min-h-8 px-3")}
        role={rail ? "img" : undefined} aria-label={rail ? `${label}: ${value}` : undefined} tabIndex={rail ? 0 : undefined}>{body}</div>
    </Tip>
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
  const lastModel = s?.transcripts.findLast((t) => ["done", "error"].includes(t.trace.model.status))?.trace.model;
  const replay = source === "fixture";
  const model = replay ? lastModel?.name ?? null : health?.llm_model ?? null;
  const [speechTone, speech]: [Tone, string] = replay ? ["neutral", "replay"] : health?.stt_loaded ? ["ok", "ready"] : ["low", "loading…"];
  // There is no rules fallback: if the extraction model isn't served, nothing is extracted (UX_PLAN §3.1.14).
  const down = !replay && health !== null && health !== undefined && health.llm_available === false;
  const [modelTone, modelText]: [Tone, string] = down ? ["high", `${model ?? "model"} not running`]
    : lastModel?.status === "error" ? ["low", "last extraction failed"]
    : model ? ["ok", model] : replay ? ["neutral", "replay"] : ["low", health ? "not configured" : "—"];
  const [linkTone, linkText] = s ? linkStatus(s.relay.link, s.relay.configured, !!s.netem) : (["neutral", "—"] as [Tone, string]);
  const cloud = s?.counters.cloud_ai_calls;
  return (
    <div className={cn("flex flex-col gap-0.5", rail && "items-center gap-1")} role="group" aria-label="On this vehicle">
      {!rail && <p className="label-caps px-3 pb-1 text-text-muted">On this vehicle</p>}
      <StatusRow rail={rail} icon={Mic} label="Speech" value={speech} tone={speechTone} />
      <StatusRow rail={rail} icon={Cpu} label="Model" value={modelText} tone={modelTone} />
      <StatusRow rail={rail} icon={ShieldCheck} label="Cloud AI" value={cloud === undefined ? "—" : `${cloud} calls`} tone={cloud ? "high" : "ok"} />
      <StatusRow rail={rail} icon={Activity} label="ED link" value={linkText} tone={linkTone} />
    </div>
  );
}

function ReplayCard({ player, rail }: { player: FixturePlayer; rail: boolean }) {
  const f = useHerald((s) => s.fixture);
  if (!f) return null;
  const toggle = () => (f.playing ? player.pause() : player.play());
  const btn = "hit grid size-9 place-items-center rounded-[9px] hover:bg-accent-fill/20";
  if (rail) {
    return (
      <Tip show label={`Replay ${f.index} / ${f.total} · not live`}>
        <button type="button" onClick={toggle} aria-label={f.playing ? "Pause replay" : "Play replay"}
          className="grid size-12 place-items-center rounded-[12px] bg-accent-tint text-herald-accent">
          {f.playing ? <Pause size={18} /> : <Play size={18} />}
        </button>
      </Tip>
    );
  }
  return (
    <div className="flex flex-col gap-2 rounded-[14px] border border-accent-fill/40 bg-accent-tint p-3 text-herald-accent" role="status" aria-label="Replay controls">
      <div className="flex items-center gap-2 text-meta font-semibold">
        <span className="rounded-full bg-accent-fill px-2 py-px text-[0.6875rem] tracking-wide text-on-accent-fill">REPLAY</span>
        <span className="truncate text-text-primary" title={`${f.name} · not live · actions are off`}>{f.name}</span>
        <span className="num ml-auto shrink-0">{f.index}/{f.total}</span>
      </div>
      <span className="block h-1 overflow-hidden rounded-full bg-accent-fill/25" aria-hidden>
        <span className="block h-full rounded-full bg-herald-accent" style={{ width: `${(f.index / Math.max(f.total, 1)) * 100}%` }} />
      </span>
      <div className="flex items-center gap-1">
        <button type="button" className={btn} onClick={toggle} aria-label={f.playing ? "Pause replay" : "Play replay"}>{f.playing ? <Pause size={16} /> : <Play size={16} />}</button>
        <button type="button" className={btn} onClick={() => player.step()} aria-label="Next recorded message"><SkipForward size={16} /></button>
        <button type="button" className={btn} onClick={() => player.restart()} aria-label="Restart replay"><RotateCcw size={16} /></button>
        <select aria-label="Replay speed" value={f.speed} onChange={(e) => player.setSpeed(Number(e.target.value))}
          className="ml-auto h-9 rounded-[9px] bg-transparent px-1 text-meta font-semibold hover:bg-accent-fill/20">
          {[1, 2, 4].map((sp) => <option key={sp} value={sp}>{sp}×</option>)}
        </select>
      </div>
    </div>
  );
}

function Settings({ rail, narrow = false }: { rail: boolean; narrow?: boolean }) {
  const ui = useHerald((s) => s.ui);
  const setUi = useHerald((s) => s.setUi);
  const btn = "hit grid size-10 place-items-center rounded-[10px] text-text-muted hover:bg-surface-1 hover:text-text-primary";
  const explain = ui.mode === "explain";
  return (
    <div className={cn("flex items-center gap-1", rail ? "flex-col" : "px-1")}>
      <Tip show label={ui.theme === "dark" ? "Light theme (Shift+L)" : "Dark theme (Shift+L)"}>
        <button type="button" className={btn} onClick={() => setUi({ theme: ui.theme === "dark" ? "light" : "dark" })} aria-label="Switch theme">
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
        <Tip show label={ui.sidebarCollapsed ? "Expand the sidebar" : "Collapse the sidebar"}>
          <button type="button" className={cn(btn, !rail && "ml-auto")} onClick={() => setUi({ sidebarCollapsed: !ui.sidebarCollapsed })}
            aria-label={ui.sidebarCollapsed ? "Expand the sidebar" : "Collapse the sidebar"}>
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
    <aside aria-label="Herald" className={cn("flex shrink-0 flex-col gap-5 overflow-y-auto py-4 transition-[width] duration-[var(--dur-short4)]",
      rail ? "w-[var(--sidebar-rail-w)] items-center px-3" : "w-[var(--sidebar-w)] px-3",
      "max-lg:w-full max-lg:flex-row max-lg:items-center max-lg:gap-3 max-lg:px-4 max-lg:py-2")}>
      <div className={cn("flex items-center gap-2.5", !rail && "px-2")}>
        <span className="grid size-9 shrink-0 place-items-center rounded-[11px] text-white shadow-[var(--shadow-1)]" style={{ backgroundImage: "linear-gradient(135deg, var(--accent-fill), #8B5CF6)" }} aria-hidden>
          <AudioLines size={19} strokeWidth={2.4} />
        </span>
        {!rail && <span className="flex flex-col max-lg:hidden"><span className="text-[1.0625rem] leading-5 font-bold tracking-tight">Herald</span><span className="text-[0.75rem] leading-4 text-text-muted">NOW · on this vehicle</span></span>}
      </div>
      <nav aria-label="Pages" className={cn("flex w-full flex-col gap-1", "max-lg:flex-row max-lg:overflow-x-auto")}>
        <NavItem rail={rail} page="overview" icon={LayoutDashboard} label="Overview" badge={a?.count} tone={a?.urgent.length ? "high" : "medium"} />
        <NavItem rail={rail} page="patient" icon={UserRound} label="Patient" />
        <NavItem rail={rail} page="trends" icon={ChartLine} label="Vitals & trends" badge={significant || undefined} tone="medium" />
        <NavItem rail={rail} page="handoff" icon={Send} label="ED handoff" badge={held || queued || undefined} tone={held ? "medium" : "low"} />
        <NavItem rail={rail} page="transcript" icon={AudioLines} label="Transcript" />
      </nav>
      <div className="flex-1 max-lg:hidden" />
      <div className="flex w-full flex-col gap-3 max-lg:hidden">
        {player && <ReplayCard player={player} rail={rail} />}
        <VehicleStatus rail={rail} />
        <div className="h-px bg-border-subtle" />
        <Settings rail={rail} />
      </div>
      <div className="ml-auto hidden items-center gap-1 max-lg:flex">
        {player && <ReplayCard player={player} rail />}
        <Settings rail={false} narrow />
      </div>
    </aside>
  );
}
