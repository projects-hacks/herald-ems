// The summary cards of the overview, one per measure, as in Health's Summary: the running clocks (last known well,
// ETA, next vitals) and the published scores (NEWS2, then the county's stroke scales, primary first; field triage for
// trauma and falls). Each card: its category glyph and title in color, a big rounded value with a gray unit, and a
// quiet footer. A score card opens its detail sheet. Copy is information, not advice (§3.0): "screen positive",
// never "LVO" or "go to".
import { Brain, ChevronRight, CircleDashed, Clock, Gauge, HeartPulse, MapPin, Navigation, Siren, type LucideIcon } from "lucide-react";
import { useState } from "react";
import { useNow } from "@/hooks/useNow";
import { elapsedAgo } from "@/lib/clock";
import { clockSeconds, hhmmss } from "@/lib/format";
import { criteriaScore, showFieldTriage, strokeScales } from "@/lib/selectors";
import { useHerald } from "@/lib/store";
import type { Alert, Clock as ClockT, News2, Snapshot, StrokeScale } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Badge, CAT_FG, ProgressBar, Value, type Cat, type Tone } from "@/components/kit";
import { Sparkline } from "@/components/Sparkline";
import { ScoreSheet, type ScoreDetail } from "@/features/scores/ScoreSheet";

function Tile({ icon: Icon, cat, label, value, unit, clock, quiet, badge, footer, onOpen, aria, wide = false }: {
  icon: LucideIcon; cat: Cat; label: string; value: string; unit?: string; clock?: boolean; quiet?: boolean;
  badge?: React.ReactNode; footer?: React.ReactNode; onOpen?: () => void; aria?: string; wide?: boolean;
}) {
  const body = (
    <>
      <span className={cn("flex min-w-0 items-center gap-1.5 text-meta font-semibold", CAT_FG[cat])}>
        <Icon size={15} strokeWidth={2.5} aria-hidden className="shrink-0" /><span className="truncate">{label}</span>
        {onOpen && <ChevronRight size={15} aria-hidden className="ml-auto shrink-0 text-text-disabled" />}
      </span>
      <span className="flex min-w-0 flex-wrap items-center gap-2">
        {clock ? <span className="flex min-w-0 flex-col gap-1"><span className="font-mono text-clock whitespace-nowrap">{value}</span>{unit && <span className="text-meta text-text-secondary">{unit}</span>}</span>
          : quiet ? <span className="text-value font-semibold text-text-muted">{value}</span>
          : <Value value={value} unit={unit} size={clock ? "clock" : "kpi"} muted={value === "—"} />}
        {badge && <span className="ml-auto shrink-0">{badge}</span>}
      </span>
      <span className="flex min-h-5 min-w-0 items-start gap-2 text-meta text-text-muted [&>span]:line-clamp-2">{footer}</span>
    </>
  );
  const cls = cn("card flex min-w-0 flex-col gap-3 px-4 py-3 text-left", wide && "col-span-full");
  return onOpen
    ? <button type="button" onClick={onOpen} aria-label={aria} className={cn(cls, "transition-[filter] duration-[var(--dur-short3)] hover:brightness-[1.08] active:brightness-95")}>{body}</button>
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
    const at0 = lkw.label.replace(/^LKW\s*/, "");
    const ago = elapsedAgo(clockSeconds(lkw, at, now));
    tiles.push(<Tile key="lkw" icon={Clock} cat="time" label="Last Known Well" value={at0} unit={`· ${ago}`} clock aria={`Last known well ${at0}, ${ago}${tap ? ", needs your tap" : ""}`}
      footer={tap ? <Badge tone="medium">needs your tap</Badge> : <>when the patient was last normal</>} />);
  } else if (s.readiness.some((r) => r.id === "stroke")) {
    tiles.push(<Tile key="lkw" icon={CircleDashed} cat="time" label="Last Known Well" value="Not asked" quiet footer="ask when last normal" />);
  }
  if (eta) {
    const left = clockSeconds(eta, at, now);
    tiles.push(<Tile key="eta" icon={Navigation} cat="time" label="ETA" value={left <= 0 ? "Arriving" : hhmmss(left)} clock={left > 0} quiet={left <= 0}
      footer={dest ? <>to {String(dest.value)}</> : "destination not set"} />);
  } else if (scene) {
    tiles.push(<Tile key="scene" icon={MapPin} cat="time" label="Call elapsed" value={hhmmss(clockSeconds(scene, at, now))} clock footer="since incident started" />);
  }
  if (due) {
    const left = clockSeconds(due, at, now);
    const every = /\(([^)]+)\)/.exec(due.label)?.[1];
    tiles.push(<Tile key="due" icon={HeartPulse} cat="time" label={left >= 0 ? "Next Vitals" : "Vitals Overdue"} value={hhmmss(left)} clock
      footer={left < 0 ? <Badge tone="low">overdue</Badge> : left <= 60 ? <Badge tone="low">due soon</Badge> : every ?? "repeat vitals"} />);
  }
  return <>{tiles}</>;
}

/** "needs air or oxygen, consciousness +1": name what a score is waiting for, so the medic knows what to ask or measure
 *  instead of reading a bare count. A mnemonic letter in front ("S Speech difficulties", G.F.A.S.T.) is dropped, then a
 *  Capitalised word is lowered; acronyms (SpO2, GCS) are left alone. */
export function needsText(missing: string[], max = 2): string {
  const low = (raw: string) => {
    const t = raw.replace(/^[A-Z] (?=[A-Z])/, "");
    return /^[A-Z][a-z]+\b/.test(t) ? t.charAt(0).toLowerCase() + t.slice(1) : t;
  };
  return `needs ${missing.slice(0, max).map(low).join(", ")}${missing.length > max ? ` +${missing.length - max}` : ""}`;
}
function news2Tone(n: News2): Tone {
  return !n.complete ? "neutral" : n.band === "high" ? "high" : n.band === "medium" || n.band === "low-medium" ? "medium" : "ok";
}

function scoreTiles(s: Snapshot, open: (d: ScoreDetail) => void, primaryOnly = false): React.ReactNode[] {
  const n = s.scores.news2;
  const history = s.scores.news2_history.filter((h) => h.complete).map((h) => h.score);
  const prev = history.length > 1 ? history[history.length - 2] : null;
  const hasVitals = Object.values(s.facts).some((fact) => fact.key.startsWith("vitals.") && fact.status === "confirmed");
  const strokeActive = s.readiness.some((item) => item.id === "stroke");
  const tiles: React.ReactNode[] = [];
  if (hasVitals || n.complete || history.length) tiles.push(
    <Tile key="news2" icon={Gauge} cat="heart" label="NEWS2" value={n.complete ? String(n.score) : "—"}
      badge={<Badge tone={news2Tone(n)}>{n.applicability === "excluded" ? "not applicable" : n.complete ? n.band : "incomplete"}</Badge>}
      footer={history.length > 1
        ? <><Sparkline values={history} width={56} height={16} label={`NEWS2 ${history.join(" to ")}`} className="text-cat-heart-fg" />{prev !== null && prev !== n.score && <span className="num">{n.score > prev ? "↑" : "↓"} from {prev}</span>}</>
        : n.applicability_reason ?? (n.complete ? "first reading" : needsText(n.missing))}
      aria={`NEWS2 ${n.applicability === "excluded" ? n.applicability_reason : n.complete ? `${n.score}, ${n.band}` : "incomplete"}. Show details.`}
      onOpen={() => open({ title: "NEWS2", cat: "heart", parts: n.parts, thresholds: n.thresholds, source: n.source, evidence: n.evidence, missing: n.missing, series: history })} />
  );
  const gfastRule = (s.alerts.find((a) => a.type === "gfast_positive") as Extract<Alert, { type: "gfast_positive" }> | undefined)?.county_rule;
  if (strokeActive) strokeScales(s).slice(0, primaryOnly ? 1 : undefined).forEach(({ id, scale }, i) =>
    tiles.push(scaleTile(id, scale, i === 0, s.county.name.replace(/,.*$/, ""), open, id === "GFAST" && scale.positive ? gfastRule : undefined)));
  if (!primaryOnly && showFieldTriage(s)) {
    const ft = s.scores.field_triage;
    tiles.push(<Tile key="ft" icon={Siren} cat="attention" label="Field Triage" value={String(ft.red.length || ft.yellow.length)} unit={ft.red.length ? "red" : ft.yellow.length ? "yellow" : "criteria"}
      footer={<span title={[...ft.red, ...ft.yellow].join("; ")}>{ft.red[0] ?? ft.yellow[0] ?? `${ft.red.length} red · ${ft.yellow.length} yellow`}{ft.red.length + ft.yellow.length > 1 ? ` +${ft.red.length + ft.yellow.length - 1}` : ""}</span>}
      aria={`Field triage: ${ft.red.length} red, ${ft.yellow.length} yellow. Show details.`}
      onOpen={() => open({ title: ft.name, cat: "attention", parts: {}, source: ft.source, missing: ft.missing, lists: [{ title: "Red criteria", tone: "high", items: ft.red }, { title: "Yellow criteria", tone: "medium", items: ft.yellow }] })} />);
  }
  if (!primaryOnly) tiles.push(...criteriaTiles(s, open));
  return tiles;
}
/** The county's own criteria (Policy 605 trauma alert, 700-A04 sepsis pre-notification, 700-A08 STEMI alert), each
 *  shown when its situation is open on this call or its criteria are met. Computed from confirmed facts only, by the
 *  deterministic criteria engine; the tile states what is met, never what to do. */
const COUNTY_CRITERIA: [id: string, checklist: string, short: string][] = [
  ["trauma_605", "trauma", "Trauma Alert (605)"], ["sepsis_700a04", "sepsis", "Sepsis (700-A04)"], ["stemi_700a08", "stemi", "STEMI Alert (700-A08)"],
];
function criteriaTiles(s: Snapshot, open: (d: ScoreDetail) => void): React.ReactNode[] {
  const active = new Set(s.readiness.map((r) => r.id));
  return COUNTY_CRITERIA.flatMap(([id, checklist, short]) => {
    const c = criteriaScore(s, id);
    if (!c || !c.applies || !(c.met || active.has(checklist))) return [];
    const hits = c.criteria.filter((r) => r.state === "met").map((r) => r.label);
    const level = c.level ?? (c.met ? "met" : null);
    const tone: Tone = c.met ? (level === "red" || level === "trigger" ? "high" : "medium") : c.complete ? "ok" : "neutral";
    return [<Tile key={id} icon={Siren} cat="attention" label={short} value={String(hits.length)}
      unit={c.met ? `${level} · ${hits.length === 1 ? "criterion" : "criteria"}` : "met"}
      badge={<Badge tone={tone}>{c.met ? "met" : c.complete ? "not met" : "incomplete"}</Badge>}
      footer={<span title={hits.join("; ")}>{hits[0] ?? (c.missing.length ? needsText(c.missing) : "no criteria met")}{hits.length > 1 ? ` +${hits.length - 1}` : ""}</span>}
      aria={`${c.name}: ${c.met ? `${level}, ${hits.length} met` : c.complete ? "not met" : "incomplete"}. Show details.`}
      onOpen={() => open({ title: c.name, cat: "attention", parts: {}, thresholds: c.thresholds ?? undefined, source: c.source, missing: c.missing,
        lists: [{ title: "Met", tone: tone === "high" ? "high" : "medium", items: hits }] })} />];
  });
}

function scaleTile(id: string, sc: StrokeScale, primary: boolean, county: string, open: (d: ScoreDetail) => void, routing?: string) {
  const max = Object.values(sc.parts).reduce((a, p) => a + (p.max ?? 0), 0) || undefined;
  const tone: Tone = !sc.complete ? "neutral" : sc.positive ? "medium" : "ok";
  return (
    <Tile key={id} icon={Brain} cat="neuro" label={sc.name} value={sc.complete ? String(sc.score) : "—"} unit={sc.complete && max ? `/ ${max}` : undefined}
      badge={<Badge tone={tone}>{sc.complete ? (sc.positive ? "positive" : "negative") : "incomplete"}</Badge>}
      footer={<>
        {sc.complete && max ? <ProgressBar frac={sc.score / max} cat="neuro" className="w-14 shrink-0" /> : <span>{needsText(sc.missing)}</span>}
        {routing ? <span className="line-clamp-2 break-words" title={routing}>{routing}</span>
          : primary && <span className="truncate" title={`${county}'s primary stroke scale`}>{sc.complete ? "primary" : "· primary"}</span>}
      </>}
      aria={`${sc.name} ${sc.complete ? `${sc.score}${max ? ` of ${max}` : ""}, screen ${sc.positive ? "positive" : "negative"}` : "incomplete"}${routing ? `. ${routing}` : primary ? `, ${county}'s primary scale` : ""}. Show details.`}
      onOpen={() => open({ title: sc.name, cat: "neuro", parts: sc.parts, thresholds: sc.thresholds, source: sc.source, evidence: sc.evidence, missing: sc.missing })} />
  );
}

/** `overview` renders the cabin overview's subset — the clocks, NEWS2 and the county's primary stroke scale;
 *  the trends panel renders every score tile under a `title` heading, and nothing at all when no score applies yet. */
export function StatTiles({ overview = false, clocks = true, title }: { overview?: boolean; clocks?: boolean; title?: string } = {}) {
  const s = useHerald((st) => st.snapshot);
  const [detail, setDetail] = useState<ScoreDetail | null>(null);
  if (!s) return null;
  const scores = scoreTiles(s, setDetail, overview);
  if (title && !clocks && !scores.length) return null;
  const grid = (
    <div className="grid shrink-0 grid-cols-[repeat(auto-fill,minmax(min(100%,15rem),1fr))] gap-3" aria-label={title ? undefined : "Clocks and scores"}>
      {clocks && <ClockTiles s={s} />}
      {scores}
      <ScoreSheet d={detail} onClose={() => setDetail(null)} />
    </div>
  );
  return title ? <section className="flex flex-col gap-2" aria-labelledby="stat-tiles-title">
    <h2 id="stat-tiles-title" className="label-caps text-text-muted">{title}</h2>{grid}
  </section> : grid;
}
