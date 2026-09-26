// Vitals: one card per vital, in the order a clinician reads a set of observations (BP, HR, SpO2, RR, temperature,
// glucose, GCS, consciousness, EtCO2, pain). Each card shows the latest confirmed value big, coloured by its clinical
// severity (config/vital_ranges.yaml) with the word beside it, where it came from and when; once a vital has two
// readings, the change, a chart and every reading with its time. A newer reading still waiting for a tap is shown
// apart from the confirmed value, never in its place. This replaces a "latest readings" strip that repeated every
// vital a second time above the trend cards.
import { ArrowDown, ArrowRight, ArrowUp, ChartLine, Gauge, Info, Monitor, TriangleAlert } from "lucide-react";
import { api } from "@/lib/api";
import { catOf, type Cat } from "@/lib/categories";
import { useContract } from "@/lib/contract";
import { useHerald } from "@/lib/store";
import { factValue, hhmm, sourceName } from "@/lib/format";
import type { Changed, FactView, Snapshot } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ActionButton } from "@/components/ActionButton";
import { StatTiles } from "@/features/overview/StatTiles";
import { Badge, CAT_ICON, CAT_STROKE, Card, CardHeader, EmptyState, PageHeader, SourceIcon, Value } from "@/components/kit";

/** A small chart of the readings: a soft area under the line, a dot per reading, the last one ringed. A reading still
 *  waiting for a tap is drawn hollow and dashed-in, so the chart never presents it as a documented value. */
function TrendChart({ values, cat, label, floor = 0, confirmed }: { values: number[]; cat: Cat; label: string; floor?: number; confirmed?: boolean[] }) {
  const w = 300, h = 72, pad = 8;
  // Keep a minimum visible span (the vital's smallest meaningful change) so a sub-threshold wobble does not fill the
  // card as dramatically as a large move.
  const lo = Math.min(...values), hi = Math.max(...values), range = hi - lo;
  const span = Math.max(range, floor) || 1;
  const base = (lo + hi) / 2 - span / 2;
  const pts = values.map((v, i) => [pad + (i / Math.max(values.length - 1, 1)) * (w - 2 * pad), h - pad - ((v - base) / span) * (h - 2 * pad)] as const);
  const color = CAT_STROKE[cat];
  const line = pts.map(([x, y]) => `${x},${y}`).join(" ");
  const area = `M${pts[0][0]},${h} L${line.replaceAll(" ", " L")} L${pts[pts.length - 1][0]},${h} Z`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-[72px] w-full" role="img" aria-label={label} preserveAspectRatio="none">
      <path d={area} fill={color} fillOpacity={0.14} />
      <polyline points={line} fill="none" stroke={color} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      {pts.map(([x, y], i) => {
        const waiting = confirmed ? confirmed[i] === false : false;
        return <circle key={i} cx={x} cy={y} r={i === pts.length - 1 ? 5 : 3.5} fill={waiting || i === pts.length - 1 ? "var(--surface-1)" : color}
          stroke={color} strokeWidth={2.5} strokeDasharray={waiting ? "2 2" : undefined} vectorEffect="non-scaling-stroke" />;
      })}
    </svg>
  );
}

/** A vital as it appears on this page. `key` is the vital that carries the trend and the severity; `extra` holds the
 *  facts shown with it (diastolic BP with systolic, the GCS components with the total, air/oxygen with SpO2). */
interface VitalCard { key: string; label: string; latest: FactView | null; waiting: FactView | null; extra: FactView[]; trend?: Changed }

// The reading order of a set of observations. A key not listed still appears, after these.
const ORDER = ["vitals.sbp", "vitals.hr", "vitals.spo2", "vitals.rr", "vitals.temp", "vitals.glucose", "vitals.gcs_total",
  "vitals.consciousness", "vitals.etco2", "vitals.pain"];
const SHOWN_WITH: Record<string, string> = {           // shown inside another vital's card, not as its own
  "vitals.dbp": "vitals.sbp", "vitals.gcs_eye": "vitals.gcs_total", "vitals.gcs_verbal": "vitals.gcs_total",
  "vitals.gcs_motor": "vitals.gcs_total", "vitals.on_oxygen": "vitals.spo2",
};
const TITLE: Record<string, string> = { "vitals.sbp": "Blood pressure", "vitals.gcs_total": "GCS" };

/** The newest confirmed reading of a key, from the current fact or, if that is still waiting, the recent timeline. */
function lastConfirmed(s: Snapshot, key: string): FactView | null {
  const f = s.facts[key];
  if (f?.status === "confirmed") return f;
  return [...s.timeline].reverse().find((t) => t.key === key && t.status === "confirmed") ?? null;
}

export function vitalCards(s: Snapshot): VitalCard[] {
  const keys = new Set<string>([...Object.keys(s.facts).filter((k) => k.startsWith("vitals.")), ...s.changed.map((c) => c.key)]);
  const main = [...keys].map((k) => SHOWN_WITH[k] ?? k);
  const ordered = [...new Set([...ORDER.filter((k) => main.includes(k)), ...main.filter((k) => !ORDER.includes(k))])];
  return ordered.flatMap((key) => {
    const latest = lastConfirmed(s, key);
    const current = s.facts[key];
    const waiting = current && current.status === "unconfirmed" ? current : null;
    const extra = Object.entries(SHOWN_WITH).filter(([, host]) => host === key).map(([k]) => lastConfirmed(s, k)).filter((f): f is FactView => !!f);
    const trend = s.changed.find((c) => c.key === key);
    if (!latest && !waiting && !trend && !extra.length) return [];
    const label = TITLE[key] ?? latest?.label ?? current?.label ?? trend?.label ?? key;
    return [{ key, label, latest, waiting, extra, trend }];
  });
}

/** Where a trend's readings came from, when the monitor supplied any: "All from the monitor" or "8 of 10 from the
 *  monitor". Nothing when none did, so a spoken-only trend is not labelled. */
export function monitorShare(trend?: Changed): string | null {
  const marks = trend?.from_monitor ?? [];
  const n = marks.filter(Boolean).length;
  if (!n) return null;
  return n === marks.length ? "All from the monitor" : `${n} of ${marks.length} from the monitor`;
}

/** The value as a clinician writes it: 162/96 for blood pressure, "9 (E2 V2 M5)" for GCS, the plain value otherwise. */
function shownValue(card: VitalCard): { value: string; unit?: string; detail?: string } {
  const f = card.latest;
  if (!f) return { value: "—" };
  const by = (k: string) => card.extra.find((e) => e.key === k);
  if (card.key === "vitals.sbp") {
    const d = by("vitals.dbp");
    return { value: d ? `${f.value}/${d.value}` : String(f.value), unit: f.unit ?? "mmHg" };
  }
  if (card.key === "vitals.gcs_total") {
    const parts = [["E", "vitals.gcs_eye"], ["V", "vitals.gcs_verbal"], ["M", "vitals.gcs_motor"]]
      .map(([l, k]) => (by(k) ? `${l}${by(k)!.value}` : null)).filter(Boolean);
    return { value: String(f.value), detail: parts.length ? parts.join(" ") : undefined };
  }
  if (card.key === "vitals.spo2") {
    const o2 = by("vitals.on_oxygen");
    return { value: String(f.value), unit: f.unit ?? "%", detail: o2 ? (o2.value ? "on oxygen" : "on room air") : undefined };
  }
  return { value: typeof f.value === "number" || typeof f.value === "string" ? String(f.value) : factValue({ value: f.value, unit: null }), unit: f.unit ?? undefined };
}

/** The card's colour: the latest value's severity, except that GCS takes the worse of the total and the motor score,
 *  because motor below 6 is a field triage criterion on its own (a total of 9 reads "out of range", motor 5 critical). */
export function cardSeverity(card: VitalCard): "abnormal" | "critical" | undefined {
  const own = card.latest?.severity;
  if (card.key !== "vitals.gcs_total") return own;
  const motor = card.extra.find((e) => e.key === "vitals.gcs_motor")?.severity;
  return own === "critical" || motor === "critical" ? "critical" : own ?? motor;
}

function Card1({ card, rule }: { card: VitalCard; rule?: string }) {
  const { latest, waiting, trend } = card;
  const cat = catOf(card.key);
  const sev = cardSeverity(card);
  const v = shownValue(card);
  const series = trend?.series;
  const d = trend ? trend.delta : undefined;
  const dir = trend?.direction ?? "flat";
  const Arrow = dir === "up" ? ArrowUp : dir === "down" ? ArrowDown : ArrowRight;
  return (
    <Card aria-label={sev ? `${card.label}, ${sev}` : card.label} data-vital={card.key}>
      <CardHeader icon={CAT_ICON[cat]} cat={cat} title={card.label} className="pb-1"
        actions={trend?.significant ? <Badge tone="medium" icon={TriangleAlert}>big change</Badge> : undefined} />
      <div className="flex flex-col gap-2 px-5 pb-4">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          {latest ? <Value value={v.value} unit={v.unit} severity={sev} />
            : <span className="text-value font-semibold text-text-muted">No confirmed value</span>}
          {d !== undefined && d !== 0 && <span className="num inline-flex items-center gap-0.5 text-body font-semibold text-text-muted"><Arrow size={15} aria-label={dir} />{d > 0 ? "+" : ""}{d}</span>}
        </div>
        {(v.detail || latest) && <p className="flex flex-wrap items-center gap-x-1.5 text-meta text-text-muted">
          {v.detail && <span className="font-semibold text-text-secondary">{v.detail}</span>}
          {v.detail && latest && <span aria-hidden>·</span>}
          {latest && <><SourceIcon capturedBy={latest.captured_by} role={latest.role} hasAudio={!!latest.provenance.audio_id} />{sourceName(latest)} · <span className="num">{hhmm(latest.ts)}</span></>}
        </p>}
        {waiting && <div className="flex flex-wrap items-center gap-2 rounded-xl border border-dashed border-medium-fg/50 px-3 py-2 text-meta">
          <span className="font-semibold text-medium-fg">Newer reading {factValue(waiting)} waiting for your tap</span>
          <span className="text-text-muted">· not used in scores or sent</span>
          {waiting.provenance.hold_reason && <span className="basis-full text-text-secondary">{waiting.provenance.hold_reason}</span>}
          <span className="ml-auto"><ActionButton pendingKey={`confirm:${waiting.id}`} onClick={() => api.confirm(waiting.id)} busyText="Confirming…" size="sm">Confirm</ActionButton></span>
        </div>}
        {series && series.length > 1 ? <>
          <TrendChart values={series} cat={cat} label={`${card.label}: ${series.join(" to ")}`} floor={trend?.floor} confirmed={trend?.confirmed} />
          <ul className="flex flex-wrap gap-x-4 gap-y-1 text-meta text-text-secondary" aria-label="Timestamped readings">
            {series.map((value, i) => <li key={i} className={cn("num", trend?.confirmed?.[i] === false && "italic text-text-muted")}
              data-source={trend?.from_monitor?.[i] ? "monitor" : undefined}>
              {trend?.times[i] ? hhmm(trend.times[i]) : "time unknown"} <b className="font-semibold text-text-primary">{value}</b>{trend?.confirmed?.[i] === false ? " (to confirm)" : ""}</li>)}
          </ul>
          {monitorShare(trend) && <p className="flex items-center gap-1.5 text-meta text-text-muted" data-testid="trend-source">
            <Monitor size={13} aria-hidden />{monitorShare(trend)}</p>}
          {trend?.significant && rule && <p className="text-meta text-text-muted">Flagged: {rule}</p>}
        </> : latest && <p className="text-meta text-text-muted">One reading so far · the trend appears with the next</p>}
      </div>
    </Card>
  );
}

function News2Trend({ s }: { s: Snapshot }) {
  const hist = s.scores.news2_history.filter((h) => h.complete);
  if (hist.length < 2) return null;
  const series = hist.map((h) => h.score);
  const d = series[series.length - 1] - series[0];
  const band = hist[hist.length - 1].band;
  const tone = band === "high" ? "high" : band === "medium" || band === "low-medium" ? "medium" : "ok";
  return (
    <Card aria-label="NEWS2 over time">
      <CardHeader icon={Gauge} cat="heart" title="NEWS2 over time" className="pb-1" actions={<Badge tone={tone}>{band}</Badge>} />
      <div className="flex flex-col gap-2 px-5 pb-4">
        <div className="flex items-baseline gap-3"><Value value={series[series.length - 1]} />
          {d !== 0 && <span className="num text-body font-semibold text-text-muted">{d > 0 ? "+" : ""}{d} since first</span>}</div>
        <TrendChart values={series} cat="heart" label={`NEWS2: ${series.join(" to ")}`} floor={2} />
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-meta text-text-secondary">{hist.map((h, i) => <li key={i} className="num">{hhmm(h.ts)} <b className="font-semibold text-text-primary">{h.score}</b></li>)}</ul>
      </div>
    </Card>
  );
}

export function TrendsPage() {
  const s = useHerald((st) => st.snapshot);
  const c = useContract();
  if (!s) return null;
  const cards = vitalCards(s);
  const confirmedCount = cards.filter((x) => x.latest).length;
  const waitingCount = cards.filter((x) => x.waiting).length;
  const excluded = s.scores.news2.applicability === "excluded";
  const scale2 = s.facts["patient.spo2_scale"]?.status === "confirmed" && Number(s.facts["patient.spo2_scale"].value) === 2;
  const newest = cards.map((x) => x.latest).filter((f): f is FactView => !!f).reduce<FactView | null>((a, b) => (!a || b.ts > a.ts ? b : a), null);
  return (
    <div className="flex flex-col gap-4 px-6 pt-5 pb-6">
      <PageHeader title="Trends & scores" description={cards.length
        ? `${confirmedCount} vital${confirmedCount === 1 ? "" : "s"} confirmed${waitingCount ? ` · ${waitingCount} newer reading${waitingCount === 1 ? "" : "s"} waiting for your tap` : ""}. Colour marks a value outside its clinical range; "big change" marks a large move.`
        : "Vitals appear here as they are heard, read from the monitor or entered."} />
      {/* Why a value is not coloured, stated rather than left for the medic to infer from silence. */}
      {excluded && <p className="flex items-start gap-2 rounded-xl border border-border-subtle bg-surface-2 px-4 py-3 text-body text-text-secondary" role="note">
        <Info size={18} aria-hidden className="mt-0.5 shrink-0 text-low-fg" />
        <span><b className="font-semibold text-text-primary">Adult ranges not applied.</b> {s.scores.news2.applicability_reason ?? "NEWS2 does not apply to this patient"}, so no value here is coloured. Judge each against the right ranges for this patient.</span>
      </p>}
      {scale2 && !excluded && <p className="flex items-start gap-2 rounded-xl border border-border-subtle bg-surface-2 px-4 py-3 text-body text-text-secondary" role="note">
        <Info size={18} aria-hidden className="mt-0.5 shrink-0 text-low-fg" />
        <span><b className="font-semibold text-text-primary">SpO₂ judged against the COPD target, 88–92%</b> (NEWS2 Scale 2, set by the medic). Other vitals use their usual ranges.</span>
      </p>}
      {/* The published scores and county criteria first: they summarise the vitals below. Each opens its detail. */}
      <StatTiles clocks={false} title="Scores" />
      {cards.length > 0 && <h2 className="label-caps text-text-muted">Vitals</h2>}
      {cards.length === 0 ? <Card><EmptyState icon={ChartLine} cat="heart" title="No vitals yet">They appear as soon as one is heard, read or entered; a trend follows the second reading.</EmptyState></Card> : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,19rem),1fr))] gap-4">
          <News2Trend s={s} />
          {cards.map((card) => <Card1 key={card.key} card={card} rule={card.trend?.significant ? c?.changeRules[card.key] : undefined} />)}
        </div>
      )}
      {/* Polite announcement of the newest confirmed reading, so a value that arrives while the medic is not looking
          is spoken by a screen reader. Urgent alerts have their own assertive region. */}
      <p className="sr-only" role="status" aria-live="polite">
        {newest && `Latest reading: ${newest.label} ${factValue(newest)}${newest.severity ? `, ${newest.severity}` : ""}`}
      </p>
    </div>
  );
}
