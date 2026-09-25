// Summary (UX_PLAN §3.1), after Health's Summary: a row of summary cards (clocks and scores), then what needs the medic
// (left, the widest column) and the pre-alert with the ED sync (right). In explain mode a third column shows what Herald heard and did. Fits 1366×768
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
      <CardHeader icon={Sparkles} cat="speech" title="Herald Thinking" id="trace-h" subtitle="What was heard and what it did"
        actions={ts.length ? <Count n={ts.length} /> : undefined} />
      <div className="min-h-0 flex-1 overflow-y-auto">
        {[...ts].reverse().map((t) => <TraceEntry key={t.id} t={t} />)}
        {ts.length === 0 && <p className="px-4 py-4 text-body text-text-muted">Nothing heard yet.</p>}
      </div>
    </Card>
  );
}

export function OverviewPage() {
  const explain = useHerald((s) => s.ui.mode === "explain");
  return (
    <div className="flex h-full flex-col gap-4 px-5 pt-4 pb-4 max-lg:h-auto">
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
