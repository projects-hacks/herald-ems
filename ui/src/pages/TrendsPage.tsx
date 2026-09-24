// Vitals & trends (UX_PLAN §3.1.9): NEWS2 over time, then each vital with two or more confirmed readings, as cards
// with the latest value, the change and a sparkline. A change past the configured rule is flagged "big change".
import { ArrowDown, ArrowRight, ArrowUp, ChartLine, TriangleAlert } from "lucide-react";
import { useContract } from "@/lib/contract";
import { useHerald } from "@/lib/store";
import type { Changed } from "@/lib/types";
import { Badge, Card, EmptyState, PageHeader } from "@/components/kit";
import { Sparkline } from "@/components/Sparkline";

function TrendCard({ label, series, delta, direction, significant, rule }: {
  label: string; series: number[]; delta?: number; direction?: Changed["direction"]; significant?: boolean; rule?: string;
}) {
  const d = delta ?? series[series.length - 1] - series[0];
  const dir = direction ?? (d > 0 ? "up" : d < 0 ? "down" : "flat");
  const Arrow = dir === "up" ? ArrowUp : dir === "down" ? ArrowDown : ArrowRight;
  return (
    <Card className="gap-3 p-5" aria-label={label}>
      <div className="flex items-center gap-2">
        <h2 className="text-title font-semibold">{label}</h2>
        {significant && <Badge tone="medium" icon={TriangleAlert} className="ml-auto" >big change</Badge>}
      </div>
      <div className="flex items-end gap-3">
        <span className="num text-kpi font-semibold tracking-display">{series[series.length - 1]}</span>
        <span className="num mb-1 inline-flex items-center gap-1 text-body text-text-secondary"><Arrow size={16} aria-label={dir} />{d > 0 ? "+" : ""}{d}</span>
      </div>
      <Sparkline values={series} width={260} height={56} label={`${label}: ${series.join(" to ")}`} className={significant ? "text-medium-fg" : "text-herald-accent"} />
      <p className="num text-meta text-text-muted">{series.join(" → ")}{rule ? ` · flagged when ${rule}` : ""}</p>
    </Card>
  );
}

export function TrendsPage() {
  const s = useHerald((st) => st.snapshot);
  const c = useContract();
  if (!s) return null;
  const news2 = s.scores.news2_history.filter((h) => h.complete).map((h) => h.score);
  const empty = s.changed.length === 0 && news2.length < 2;
  return (
    <div className="flex flex-col gap-5 p-6">
      <PageHeader title="Vitals & trends" description="Confirmed readings over time. A trend appears once a vital has two readings." />
      {empty ? <Card><EmptyState icon={ChartLine} tone="neutral" title="No trends yet">Once a vital has two confirmed readings, its trend shows here.</EmptyState></Card> : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(18rem,1fr))] gap-4">
          {news2.length > 1 && <TrendCard label="NEWS2" series={news2} />}
          {s.changed.map((t) => <TrendCard key={t.key} label={t.label} series={t.series} delta={t.delta} direction={t.direction} significant={t.significant} rule={t.significant ? c?.changeRules[t.key] : undefined} />)}
        </div>
      )}
    </div>
  );
}
