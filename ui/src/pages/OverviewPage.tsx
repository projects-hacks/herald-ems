// Overview (UX_PLAN §3.1): the KPI row (clocks and scores), then what needs the medic (left, the widest column) and the
// pre-alert with the ED sync (right). In explain mode a third column shows what Herald heard and did. Fits 1366×768
// without page scrolling; each card scrolls inside itself. Below 1024 px everything stacks in the §3.1.1 order.
import { Sparkles } from "lucide-react";
import { useHerald } from "@/lib/store";
import { cn } from "@/lib/utils";
import { Card, CardHeader, Count } from "@/components/kit";
import { AttentionQueue } from "@/features/attention/AttentionQueue";
import { PreAlertCard } from "@/features/overview/PreAlertCard";
import { StatTiles } from "@/features/overview/StatTiles";
import { TraceEntry } from "@/features/trace/trace";

function TracePanel({ className }: { className?: string }) {
  const ts = useHerald((s) => s.snapshot?.transcripts) ?? [];
  return (
    <Card aria-labelledby="trace-h" className={className}>
      <CardHeader icon={Sparkles} title="Herald thinking" id="trace-h" subtitle="What was heard and what it did"
        badge={ts.length ? <Count n={ts.length} /> : undefined} />
      <div className="min-h-0 flex-1 overflow-y-auto border-t border-border-subtle">
        {[...ts].reverse().map((t) => <TraceEntry key={t.id} t={t} />)}
        {ts.length === 0 && <p className="px-4 py-4 text-body text-text-muted">Nothing heard yet.</p>}
      </div>
    </Card>
  );
}

export function OverviewPage() {
  const explain = useHerald((s) => s.ui.mode === "explain");
  return (
    <div className="mx-auto flex h-full w-full max-w-[1600px] flex-col gap-4 px-7 py-5 max-lg:h-auto max-lg:px-5">
      <div className="flex min-h-7 shrink-0 items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <span className="size-2 rounded-full bg-herald-accent" aria-hidden />
          <h2 className="text-title font-semibold tracking-display">Live patient overview</h2>
        </div>
        <p className="hidden text-meta text-text-muted sm:block">Confirmed information updates here automatically</p>
      </div>
      <StatTiles />
      <div className={cn("grid min-h-0 flex-1 gap-4 max-lg:flex max-lg:flex-col",
        explain ? "grid-cols-[minmax(0,1fr)_minmax(0,21rem)_minmax(0,24rem)]" : "grid-cols-[minmax(0,1fr)_minmax(0,25rem)]")}>
        <AttentionQueue />
        <PreAlertCard />
        {explain && <TracePanel className="max-lg:min-h-96" />}
      </div>
    </div>
  );
}
