// Vitals & trends, like Health's trend cards: NEWS2 over time, then each vital with two or more
// confirmed readings. Each card: the title in its category color, the latest value big and rounded with the change,
// and a chart of the readings. A change past the configured rule is flagged "big change".
import { ArrowDown, ArrowRight, ArrowUp, ChartLine, Gauge, TriangleAlert } from "lucide-react";
import { catOf, type Cat } from "@/lib/categories";
import { useContract } from "@/lib/contract";
import { useHerald } from "@/lib/store";
import { factValue, hhmm } from "@/lib/format";
import type { Changed } from "@/lib/types";
import { Badge, CAT_ICON, CAT_STROKE, Card, CardHeader, EmptyState, PageHeader, Value } from "@/components/kit";

/** A small chart of the readings: a soft area under the line, a dot per reading, the last one ringed. */
function TrendChart({ values, cat, label }: { values: number[]; cat: Cat; label: string }) {
  const w = 300, h = 84, pad = 8;
  const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
  const pts = values.map((v, i) => [pad + (i / Math.max(values.length - 1, 1)) * (w - 2 * pad), h - pad - ((v - lo) / span) * (h - 2 * pad)] as const);
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

function TrendCard({ label, cat, series, delta, direction, significant, rule, times, unit }: {
  label: string; cat: Cat; series: number[]; delta?: number; direction?: Changed["direction"]; significant?: boolean; rule?: string; times?: string[]; unit?: string;
}) {
  const d = delta ?? series[series.length - 1] - series[0];
  const dir = direction ?? (d > 0 ? "up" : d < 0 ? "down" : "flat");
  const Arrow = dir === "up" ? ArrowUp : dir === "down" ? ArrowDown : ArrowRight;
  return (
    <Card aria-label={label}>
      <CardHeader icon={label === "NEWS2" ? Gauge : CAT_ICON[cat]} cat={cat} title={label} className="pb-1"
        actions={significant ? <Badge tone="medium" icon={TriangleAlert}>big change</Badge> : undefined} />
      <div className="flex flex-col gap-2 px-5 pb-4">
        <div className="flex items-baseline gap-3">
          <Value value={series[series.length - 1]} unit={unit} />
          <span className="num inline-flex items-center gap-0.5 text-body font-semibold text-text-muted"><Arrow size={15} aria-label={dir} />{d > 0 ? "+" : ""}{d}</span>
        </div>
        <TrendChart values={series} cat={cat} label={`${label}: ${series.join(" to ")}`} />
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
          {latest.map((fact) => <div key={fact.id}><p className="text-meta text-text-muted">{fact.label}</p>
            <p className="text-critical font-semibold">{factValue(fact)}</p><p className="text-meta text-text-muted">Captured {hhmm(fact.ts)}</p></div>)}
        </div>
      </Card>}
      {empty ? <Card><EmptyState icon={ChartLine} cat="heart" title="No trends yet">Once a vital has two confirmed readings, its trend shows here.</EmptyState></Card> : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(18rem,1fr))] gap-4">
          {news2.length > 1 && <TrendCard label="NEWS2" cat="heart" series={news2} times={s.scores.news2_history.filter((h) => h.complete).map((h) => h.ts)} />}
          {s.changed.map((t) => <TrendCard key={t.key} label={t.label} cat={catOf(t.key)} series={t.series} times={t.times} unit={c?.keys[t.key]?.unit} delta={t.delta} direction={t.direction} significant={t.significant} rule={t.significant ? c?.changeRules[t.key] : undefined} />)}
        </div>
      )}
    </div>
  );
}
