// The KPI row of the overview: the running clocks (last known well, ETA, next vitals) and the published scores
// (NEWS2, then the county's stroke scales, primary first; field triage for trauma and falls). A score tile opens its
// detail sheet. Copy is information, not advice (§3.0): "screen positive", never "LVO" or "go to".
import { Brain, CircleDashed, Clock, Gauge, HeartPulse, MapPin, Navigation, Siren, type LucideIcon } from "lucide-react";
import { useState } from "react";
import { useNow } from "@/hooks/useNow";
import { clockSeconds, hhmmss } from "@/lib/format";
import { showFieldTriage, strokeScales } from "@/lib/selectors";
import { useHerald } from "@/lib/store";
import type { Clock as ClockT, News2, Snapshot, StrokeScale } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Badge, Dot, ProgressBar, type Tone } from "@/components/kit";
import { Sparkline } from "@/components/Sparkline";
import { ScoreSheet, type ScoreDetail } from "@/features/scores/ScoreSheet";

function Tile({ icon: Icon, label, value, unit, mono, quiet, badge, footer, onOpen, aria, marker }: {
  icon: LucideIcon; label: string; value: string; unit?: string; mono?: boolean; quiet?: boolean; badge?: React.ReactNode;
  footer?: React.ReactNode; onOpen?: () => void; aria?: string; marker?: React.ReactNode;
}) {
  const body = (
    <>
      <span className="flex min-w-0 items-center gap-2 text-meta font-medium text-text-muted">
        <Icon size={15} aria-hidden className="shrink-0" /><span className="truncate">{label}</span>{marker}
      </span>
      <span className="flex min-w-0 items-center gap-2">
        <span className={cn("num truncate font-semibold tracking-display", mono ? "font-mono text-clock" : quiet ? "text-value leading-9" : "text-kpi",
          (value === "—" || quiet) && "text-text-muted")}>{value}</span>
        {unit && <span className="num self-end pb-1 text-body font-medium text-text-muted">{unit}</span>}
        {badge && <span className="ml-auto shrink-0">{badge}</span>}
      </span>
      <span className="flex min-h-5 min-w-0 items-center gap-2 truncate text-meta text-text-muted">{footer}</span>
    </>
  );
  const cls = "card flex min-w-0 flex-col justify-between gap-1 px-4 py-3 text-left";
  return onOpen
    ? <button type="button" onClick={onOpen} aria-label={aria} className={cn(cls, "transition-colors duration-[var(--dur-short3)] hover:border-border-control/60 hover:bg-surface-2")}>{body}</button>
    : <div className={cls} role="group" aria-label={aria}>{body}</div>;
}

function ClockTiles({ s }: { s: Snapshot }) {
  const at = useHerald((st) => st.lastStateAt);
  const now = useNow();
  const clock = (id: ClockT["id"]) => s.clocks.find((c) => c.id === id);
  const lkw = clock("lkw"), eta = clock("eta"), scene = clock("scene"), due = clock("reassess");
  const lkwFact = s.facts["stroke.lkw"];
  const dest = s.facts["transport.destination"];
  const tiles: React.ReactNode[] = [];
  if (lkw) {
    const tap = lkwFact?.status === "unconfirmed";
    const v = `+${hhmmss(clockSeconds(lkw, at, now))}`;
    tiles.push(<Tile key="lkw" icon={Clock} label="Last known well" value={v} mono aria={`Last known well ${lkw.label.replace(/^LKW\s*/, "")}, ${v} ago${tap ? ", needs your tap" : ""}`}
      footer={tap ? <Badge tone="medium">needs your tap</Badge> : <>at {lkw.label.replace(/^LKW\s*/, "")}</>} />);
  } else if (s.readiness.some((r) => r.id === "stroke")) {
    tiles.push(<Tile key="lkw" icon={CircleDashed} label="Last known well" value="Not asked" quiet footer="ask when last normal" />);
  }
  if (eta) {
    const left = clockSeconds(eta, at, now);
    tiles.push(<Tile key="eta" icon={Navigation} label="ETA" value={left <= 0 ? "Arriving" : hhmmss(left)} mono={left > 0}
      footer={dest ? <>to {String(dest.value)}</> : "destination not set"} />);
  } else if (scene) {
    tiles.push(<Tile key="scene" icon={MapPin} label="On scene" value={hhmmss(clockSeconds(scene, at, now))} mono footer="since arrival" />);
  }
  if (due) {
    const left = clockSeconds(due, at, now);
    const every = /\(([^)]+)\)/.exec(due.label)?.[1];
    tiles.push(<Tile key="due" icon={HeartPulse} label={left >= 0 ? "Next vitals" : "Vitals overdue"} value={hhmmss(left)} mono
      footer={left < 0 ? <Badge tone="low">overdue</Badge> : left <= 60 ? <Badge tone="low">due soon</Badge> : every ?? "repeat vitals"} />);
  }
  return <>{tiles}</>;
}

function news2Tone(n: News2): Tone {
  return !n.complete ? "neutral" : n.band === "high" ? "high" : n.band === "medium" || n.band === "low-medium" ? "medium" : "ok";
}

function ScoreTiles({ s, open }: { s: Snapshot; open: (d: ScoreDetail) => void }) {
  const n = s.scores.news2;
  const history = s.scores.news2_history.filter((h) => h.complete).map((h) => h.score);
  const prev = history.length > 1 ? history[history.length - 2] : null;
  const tiles: React.ReactNode[] = [
    <Tile key="news2" icon={Gauge} label="NEWS2" value={n.complete ? String(n.score) : "—"}
      badge={<Badge tone={news2Tone(n)}>{n.complete ? n.band : "incomplete"}</Badge>}
      footer={history.length > 1
        ? <><Sparkline values={history} width={56} height={16} label={`NEWS2 ${history.join(" to ")}`} className="text-herald-accent" />{prev !== null && prev !== n.score && <span className="num">{n.score > prev ? "↑" : "↓"} from {prev}</span>}</>
        : n.complete ? "first reading" : `needs ${n.missing.length} more`}
      aria={`NEWS2 ${n.complete ? `${n.score}, ${n.band}` : "incomplete"}. Show details.`}
      onOpen={() => open({ title: "NEWS2", parts: n.parts, thresholds: n.thresholds, source: n.source, evidence: n.evidence, missing: n.missing, series: history })} />,
  ];
  strokeScales(s).forEach(({ id, scale }, i) => tiles.push(scaleTile(id, scale, i === 0, s.county.name.replace(/,.*$/, ""), open)));
  if (showFieldTriage(s)) {
    const ft = s.scores.field_triage;
    tiles.push(<Tile key="ft" icon={Siren} label="Field triage" value={ft.red.length ? `${ft.red.length} red` : ft.yellow.length ? `${ft.yellow.length} yellow` : "none"}
      badge={ft.red.length ? <Badge tone="high">red</Badge> : ft.yellow.length ? <Badge tone="medium">yellow</Badge> : undefined}
      footer={`${ft.red.length} red · ${ft.yellow.length} yellow`} aria="Field triage. Show details."
      onOpen={() => open({ title: ft.name, parts: {}, source: ft.source, missing: ft.missing, lists: [{ title: "Red criteria", tone: "high", items: ft.red }, { title: "Yellow criteria", tone: "medium", items: ft.yellow }] })} />);
  }
  return <>{tiles}</>;
}

function scaleTile(id: string, sc: StrokeScale, primary: boolean, county: string, open: (d: ScoreDetail) => void) {
  const max = Object.values(sc.parts).reduce((a, p) => a + (p.max ?? 0), 0) || undefined;
  const tone: Tone = !sc.complete ? "neutral" : sc.positive ? "medium" : "ok";
  return (
    <Tile key={id} icon={Brain} label={sc.name} value={sc.complete ? String(sc.score) : "—"} unit={sc.complete && max ? `/${max}` : undefined}
      badge={<Badge tone={tone}>{sc.complete ? (sc.positive ? "positive" : "negative") : "incomplete"}</Badge>}
      footer={<>
        {sc.complete && max ? <ProgressBar frac={sc.score / max} tone={tone === "ok" ? "ok" : "medium"} className="w-14 shrink-0" /> : <span>needs {sc.missing.length} more</span>}
        {primary && <span className="inline-flex items-center gap-1 truncate" title={`${county}'s primary stroke scale`}><Dot tone="accent" className="size-1.5" />primary</span>}
      </>}
      aria={`${sc.name} ${sc.complete ? `${sc.score}${max ? ` of ${max}` : ""}, screen ${sc.positive ? "positive" : "negative"}` : "incomplete"}${primary ? `, ${county}'s primary scale` : ""}. Show details.`}
      onOpen={() => open({ title: sc.name, parts: sc.parts, thresholds: sc.thresholds, source: sc.source, evidence: sc.evidence, missing: sc.missing })} />
  );
}

export function StatTiles() {
  const s = useHerald((st) => st.snapshot);
  const [detail, setDetail] = useState<ScoreDetail | null>(null);
  if (!s) return null;
  return (
    <div className="grid shrink-0 grid-cols-[repeat(auto-fit,minmax(10.5rem,1fr))] gap-3" aria-label="Clocks and scores">
      <ClockTiles s={s} />
      <ScoreTiles s={s} open={setDetail} />
      <ScoreSheet d={detail} onClose={() => setDetail(null)} />
    </div>
  );
}
