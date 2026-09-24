// The detail sheet behind a score tile (UX_PLAN §3.1.7): every part, the thresholds and the published source.
// Computed by plain code from confirmed facts only.
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { formatValue } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Sparkline } from "@/components/Sparkline";

export interface ScoreDetail {
  title: string;
  parts: Record<string, { value: unknown; points: number; max?: number }>;
  thresholds?: string; source: string; evidence?: string; missing: string[]; series?: number[];
  lists?: { title: string; tone: "high" | "medium"; items: string[] }[];
}

export function ScoreSheet({ d, onClose }: { d: ScoreDetail | null; onClose: () => void }) {
  const parts = d ? Object.entries(d.parts) : [];
  const hasMax = parts.some(([, p]) => p.max !== undefined);
  return (
    <Sheet open={!!d} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="w-[28rem] max-w-full gap-0 border-border-subtle bg-surface-3 sm:max-w-md">
        {d && <>
          <SheetHeader className="px-6 pt-6">
            <SheetTitle className="text-value font-bold">{d.title}</SheetTitle>
            <SheetDescription className="text-body text-text-muted">Computed from confirmed facts only.</SheetDescription>
          </SheetHeader>
          <div className="flex flex-col gap-5 overflow-y-auto px-6 pb-6 text-body">
            {parts.length > 0 && (
              <table className="w-full">
                <thead className="text-meta text-text-muted"><tr><th className="py-1 text-left font-medium">Parameter</th><th className="text-left font-medium">Value</th><th className="text-right font-medium">Points</th>{hasMax && <th className="text-right font-medium">Max</th>}</tr></thead>
                <tbody className="num divide-y divide-border-subtle">
                  {parts.map(([name, p]) => (
                    <tr key={name}><td className="py-2">{name}</td><td>{formatValue(p.value as never)}</td><td className="text-right font-semibold">{p.points}</td>{hasMax && <td className="text-right text-text-muted">{p.max}</td>}</tr>
                  ))}
                </tbody>
              </table>
            )}
            {d.lists?.map((l) => (
              <div key={l.title}>
                <p className="font-semibold">{l.title} · {l.items.length}</p>
                {l.items.length ? l.items.map((x) => <p key={x} className={cn(l.tone === "high" ? "text-high-fg" : "text-medium-fg")}>{x}</p>) : <p className="text-text-muted">None</p>}
              </div>
            ))}
            {d.missing.length > 0 && <p><span className="font-semibold">Missing inputs:</span> {d.missing.join(", ")}</p>}
            {d.series && d.series.length > 1 && <p className="flex items-center gap-3"><Sparkline values={d.series} label={`history ${d.series.join(" to ")}`} /><span className="num">{d.series.join(" → ")}</span></p>}
            <div className="flex flex-col gap-2 rounded-[14px] bg-surface-2 p-3 text-text-secondary">
              {d.thresholds && <p><span className="font-semibold text-text-primary">Thresholds.</span> {d.thresholds}</p>}
              <p><span className="font-semibold text-text-primary">Source.</span> {d.source}</p>
              {d.evidence && <p><span className="font-semibold text-text-primary">Evidence.</span> {d.evidence}</p>}
            </div>
          </div>
        </>}
      </SheetContent>
    </Sheet>
  );
}
