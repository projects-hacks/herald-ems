// The pre-alert card of the overview: the active checklist (how many items are captured, each item's state) and,
// below it, whether the receiving ED has it (sent / queued / held, reconciled), with a way into the full ED handoff.
// Gap-first (P2): missing items are listed with the rest, dashed and bold, so what to ask next is visible at a glance.
import { ArrowRight, CircleCheck, CircleDashed, CircleQuestionMark, Send } from "lucide-react";
import { useHerald } from "@/lib/store";
import type { ReadinessItem, Snapshot } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Badge, Button, Card, CardHeader, Dot, SegmentBar } from "@/components/kit";
import { AuthorizeForm, Figure, LinkDownNote, ReconciledLine, useHandoff } from "@/features/handoff/handoff";

const ITEM: Record<ReadinessItem["state"], { icon: typeof CircleCheck; cls: string; word: string }> = {
  done: { icon: CircleCheck, cls: "text-ok-fg", word: "done" },
  pending: { icon: CircleQuestionMark, cls: "text-medium-fg", word: "needs your tap" },
  missing: { icon: CircleDashed, cls: "text-text-muted", word: "missing" },
};

function EdSummary({ s }: { s: Snapshot }) {
  const setUi = useHerald((st) => st.setUi);
  const { sent, queued, held } = useHandoff(s);
  const r = s.relay;
  if (!r.configured) return <p className="text-body text-text-muted">The ED link isn't set up on this vehicle.</p>;
  if (!r.authorized) return <AuthorizeForm s={s} />;
  return (
    <div className="flex flex-col gap-2.5">
      <div className="grid grid-cols-3 gap-2">
        <Figure n={sent} label="sent" tone="text-ok-fg" />
        <Figure n={queued} label="queued" tone={queued ? "text-low-fg" : "text-text-muted"} />
        <Figure n={held} label="held here" tone={held ? "text-medium-fg" : "text-text-muted"} />
      </div>
      {r.link === "down" && <LinkDownNote />}
      <div className="flex items-center gap-2">
        <ReconciledLine s={s} />
        <Button size="sm" variant="ghost" onClick={() => setUi({ page: "handoff" })} className="ml-auto text-herald-accent">
          Details<ArrowRight size={15} aria-hidden />
        </Button>
      </div>
    </div>
  );
}

export function PreAlertCard({ className }: { className?: string }) {
  const s = useHerald((st) => st.snapshot);
  if (!s) return <Card className={cn("p-5", className)}><p className="text-critical text-text-muted">—</p></Card>;
  const r = s.readiness[0];
  const relay = s.relay;
  return (
    <Card id="prealert" tabIndex={-1} aria-labelledby="pa-h" className={cn("outline-none", className)}>
      <CardHeader icon={Send} tone={r?.ready ? "ok" : "accent"} id="pa-h" title={r ? r.label : "Pre-alert"}
        subtitle={r ? "Pre-alert checklist" : `Dispatch: ${s.incident.dispatch ?? "unknown"}`}
        badge={r && (r.ready ? <Badge tone="ok" icon={CircleCheck}>Ready</Badge> : <Badge tone="medium">{r.total - r.done} to go</Badge>)}
        actions={r && <span className="num text-value font-semibold">{r.done}<span className="text-body font-medium text-text-muted">/{r.total}</span></span>} />
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-5 pb-4">
        {r ? (
          <div className="@container flex flex-col gap-2.5">
            <SegmentBar states={r.items.map((i) => i.state)} />
            <ul className="grid grid-cols-2 gap-x-3 @max-[20rem]:grid-cols-1" aria-label="Checklist items">
              {r.items.map((i) => {
                const it = ITEM[i.state];
                return (
                  <li key={i.key} className="flex min-h-10 items-center gap-2 border-b border-border-subtle py-1.5 text-body leading-tight">
                    <it.icon size={17} strokeWidth={2.2} aria-hidden className={cn("shrink-0", it.cls)} />
                    <span className={cn("min-w-0", i.state === "done" ? "text-text-secondary" : "font-semibold text-text-primary")}>{i.label}</span>
                    <span className="sr-only">{it.word}</span>
                  </li>
                );
              })}
            </ul>
            {r.items.some((i) => i.state !== "done") && (
              <p className="flex flex-wrap gap-x-4 gap-y-1 text-meta text-text-muted">
                <span className="inline-flex items-center gap-1.5"><CircleDashed size={14} aria-hidden />missing</span>
                <span className="inline-flex items-center gap-1.5"><CircleQuestionMark size={14} aria-hidden className="text-medium-fg" />needs your tap</span>
              </p>
            )}
          </div>
        ) : (
          <p className="text-body text-text-muted">No pre-alert checklist for this dispatch yet.</p>
        )}
        <div className="flex flex-col gap-2.5 rounded-[14px] border border-border-subtle p-3">
          <div className="flex items-center gap-2">
            <h3 className="label-caps shrink-0 text-text-muted">ED sync</h3>
            {relay.authorized && (
              <span className="ml-auto inline-flex min-w-0 items-center gap-1.5 text-meta text-text-secondary">
                <Dot tone={relay.link === "good" ? "ok" : "low"} /><span className="truncate">{relay.authorized.destination} · {relay.link === "down" ? "offline" : relay.link}</span>
              </span>
            )}
          </div>
          <EdSummary s={s} />
        </div>
      </div>
    </Card>
  );
}
