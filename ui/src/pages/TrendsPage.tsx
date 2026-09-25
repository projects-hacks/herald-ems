// Vitals & trends, like Health's trend cards: NEWS2 over time, then each vital with two or more
// confirmed readings. Each card: the title in its category color, the latest value big and rounded with the change,
// and a chart of the readings. A change past the configured rule is flagged "big change".
import { ArrowDown, ArrowRight, ArrowUp, ChartLine, Gauge, TriangleAlert } from "lucide-react";
import { catOf, type Cat } from "@/lib/categories";
import { useContract } from "@/lib/contract";
import { useHerald } from "@/lib/store";
import { factValue, hhmm } from "@/lib/format";
import type { Changed } from "@/lib/types";
import { Badge, CAT_ICON, CAT_STROKE, Card, CardHeader, EmptyState, PageHeader, SEVERITY, SeverityBadge, SourceIcon, TEXT, Value } from "@/components/kit";
import { cn } from "@/lib/utils";

/** A small chart of the readings: a soft area under the line, a dot per reading, the last one ringed. */
function TrendChart({ values, cat, label, floor = 0 }: { values: number[]; cat: Cat; label: string; floor?: number }) {
  const w = 300, h = 84, pad = 8;
  // Auto-scaling to the data's own min/max made a 2-point wobble fill the card as dramatically as a 40-point drop.
  // Enforce a minimum visible span (`floor`, a per-vital minimum meaningful change) so a small movement reads as
  // small and a large one reads as large. The line still centres in the band, so it is never clipped.
  const lo = Math.min(...values), hi = Math.max(...values), range = hi - lo;
  const span = Math.max(range, floor) || 1;
  const mid = (lo + hi) / 2, base = mid - span / 2;
  const pts = values.map((v, i) => [pad + (i / Math.max(values.length - 1, 1)) * (w - 2 * pad), h - pad - ((v - base) / span) * (h - 2 * pad)] as const);
  const color = CAT_STROKE[cat];
  const line = pts.map(([x, y]) => `${x},${y}`).join(" ");
  const area = `M${pts[0][0]},${h} L${line.replaceAll(" ", " L")} L${pts[pts.length - 1][0]},${h} Z`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-[84px] w-full" role="img" aria-label={label} preserveAspectRatio="none">
      <path d={area} fill={color} fillOpacity={0.14} />
      <polyline points={line} fill="none" stroke={color} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      {pts.map(([x, y], i) => <circle key={i} cx={x} cy={y} r={i === pts.length - 1 ? 5 : 3.5} fill={i === pts.length - 1 ? "var(--surface-1)" : color} stroke={color} strokeWidth={2.5} vectorEffect="non-scaling-stroke" />)}
    </svg>
  );
}

function TrendCard({ label, cat, series, delta, direction, significant, severity, rule, times, unit, floor }: {
  label: string; cat: Cat; series: number[]; delta?: number; direction?: Changed["direction"]; significant?: boolean;
  severity?: Changed["severity"]; rule?: string; times?: string[]; unit?: string; floor?: number;
}) {
  const d = delta ?? series[series.length - 1] - series[0];
  const dir = direction ?? (d > 0 ? "up" : d < 0 ? "down" : "flat");
  const Arrow = dir === "up" ? ArrowUp : dir === "down" ? ArrowDown : ArrowRight;
  // Two independent signals, both shown when both hold: `severity` = the value is out of a clinical range
  // (config/vital_ranges.yaml), `significant` = it moved past a change rule (config/trends.yaml). A value can be
  // abnormal without moving and can move without being abnormal, so neither implies the other.
  return (
    <Card aria-label={severity ? `${label}, ${severity}` : label}>
      <CardHeader icon={label === "NEWS2" ? Gauge : CAT_ICON[cat]} cat={cat} title={label} className="pb-1"
        actions={significant ? <Badge tone="medium" icon={TriangleAlert}>big change</Badge> : undefined} />
      <div className="flex flex-col gap-2 px-5 pb-4">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <Value value={series[series.length - 1]} unit={unit} severity={severity} />
          <span className="num inline-flex items-center gap-0.5 text-body font-semibold text-text-muted"><Arrow size={15} aria-label={dir} />{d > 0 ? "+" : ""}{d}</span>
        </div>
        <TrendChart values={series} cat={cat} label={`${label}: ${series.join(" to ")}`} floor={floor} />
        <p className="num text-meta text-text-muted">{series.join(" → ")}{rule ? ` · flagged when ${rule}` : ""}</p>
        {times && <ul className="flex flex-wrap gap-x-4 gap-y-1 text-meta text-text-secondary" aria-label="Timestamped readings">
          {series.map((value, index) => <li key={index}>{times[index] ? hhmm(times[index]) : "Time unknown"}: {value} {unit}</li>)}
        </ul>}
      </div>
    </Card>
  );
}

export function TrendsPage() {
  const s = useHerald((st) => st.snapshot);
  const c = useContract();
  if (!s) return null;
  const news2 = s.scores.news2_history.filter((h) => h.complete).map((h) => h.score);
  const empty = s.changed.length === 0 && news2.length < 2;
  const latest = Object.values(s.facts).filter((fact) => fact.key.startsWith("vitals.") && fact.status === "confirmed");
  return (
    <div className="flex flex-col gap-5 px-6 pt-5 pb-6">
      <PageHeader title="Vitals" description="Confirmed readings over time. A trend appears once a vital has two readings." />
      {latest.length > 0 && <Card className="p-5"><h2 className="mb-3 text-title font-semibold">Latest confirmed readings</h2>
        <div className="grid grid-cols-[repeat(auto-fit,minmax(9rem,1fr))] gap-4">
          {latest.map((fact) => {
            const sev = fact.severity ? SEVERITY[fact.severity] : null;
            return (
              <div key={fact.id} aria-label={sev ? `${fact.label}, ${fact.severity}` : fact.label}>
                <p className="flex items-center gap-1.5 text-meta text-text-muted">
                  <SourceIcon capturedBy={fact.captured_by} hasAudio={!!fact.provenance.audio_id} />{fact.label}
                </p>
                <p className={cn("text-critical font-semibold", sev ? TEXT[sev.tone] : undefined)}>{factValue(fact)}</p>
                {sev && <SeverityBadge severity={fact.severity!} className="mt-0.5" />}
                <p className="text-meta text-text-muted">Captured {hhmm(fact.ts)}</p>
              </div>
            );
          })}
        </div>
      </Card>}
      {/* Polite announcement of the newest confirmed reading, so a value that arrives while the medic is not looking
          is spoken by a screen reader. Urgent alerts have their own assertive region (CabinApp); this is the routine
          "a reading landed" channel that the tiles otherwise lacked. */}
      <p className="sr-only" role="status" aria-live="polite">
        {latest.length > 0 && (() => {
          const newest = latest.reduce((a, b) => (b.ts > a.ts ? b : a));
          const sev = newest.severity ? `, ${newest.severity}` : "";
          return `Latest reading: ${newest.label} ${factValue(newest)}${sev}`;
        })()}
      </p>
      {empty ? <Card><EmptyState icon={ChartLine} cat="heart" title="No trends yet">Once a vital has two confirmed readings, its trend shows here.</EmptyState></Card> : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(18rem,1fr))] gap-4">
          {news2.length > 1 && <TrendCard label="NEWS2" cat="heart" series={news2} times={s.scores.news2_history.filter((h) => h.complete).map((h) => h.ts)} />}
          {s.changed.map((t) => <TrendCard key={t.key} label={t.label} cat={catOf(t.key)} series={t.series} times={t.times} unit={c?.keys[t.key]?.unit} delta={t.delta} direction={t.direction} significant={t.significant} severity={t.severity} floor={t.floor} rule={t.significant ? c?.changeRules[t.key] : undefined} />)}
        </div>
      )}
    </div>
  );
}
