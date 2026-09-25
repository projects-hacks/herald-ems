// The pre-alert card of the summary: an Activity-style ring for the active checklist, each item's state as a list,
// then whether the receiving ED has it (sent / queued / held, reconciled), with a way into the full ED handoff.
// Gap-first (P2): missing items are listed with the rest, dashed and bold, so what to ask next is visible at a glance.
import { useState } from "react";
import { ChevronRight, CircleCheck, CircleDashed, CircleQuestionMark, ListChecks, Send } from "lucide-react";
import { useHerald } from "@/lib/store";
import type { ReadinessItem, Snapshot } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Badge, Button, Card, CardHeader, Dot, Ring } from "@/components/kit";
import { AuthorizeForm, Figure, LinkDownNote, ReconciledLine, useHandoff } from "@/features/handoff/handoff";

const ITEM: Record<ReadinessItem["state"], { icon: typeof CircleCheck; cls: string; word: string }> = {
  done: { icon: CircleCheck, cls: "text-cat-check-fg", word: "done" },
  pending: { icon: CircleQuestionMark, cls: "text-medium-fg", word: "needs your tap" },
  missing: { icon: CircleDashed, cls: "text-text-muted", word: "missing" },
};

function EdSync({ s }: { s: Snapshot }) {
  const setUi = useHerald((st) => st.setUi);
  const { sent, queued, held } = useHandoff(s);
  const r = s.relay;
  return (
    <div className="flex flex-col gap-3 border-t border-border-subtle pt-3.5">
      <div className="flex items-center gap-2">
        <Send size={16} strokeWidth={2.4} aria-hidden className="text-cat-ed-fg" />
        <h3 className="text-title font-semibold text-cat-ed-fg">ED Sync</h3>
        {r.authorized && (
          <span className="ml-auto inline-flex min-w-0 items-center gap-1.5 text-meta text-text-muted">
            <Dot tone={r.link === "good" ? "ok" : "low"} /><span className="truncate">{r.authorized.destination} · {r.link === "down" ? "offline" : `link ${r.link}`}</span>
          </span>
        )}
      </div>
      {!r.configured ? <p className="text-body text-text-muted">The ED link isn't set up on this vehicle.</p>
        : !r.authorized ? <AuthorizeForm s={s} />
        : <>
          <div className="grid grid-cols-3 gap-2">
            <Figure n={sent} label="sent" tone="text-ok-fg" />
            <Figure n={queued} label="queued" tone={queued ? "text-low-fg" : "text-text-muted"} />
            <Figure n={held} label="held here" tone={held ? "text-medium-fg" : "text-text-muted"} />
          </div>
          {r.link === "down" && <LinkDownNote />}
          <div className="flex items-center gap-2">
            <ReconciledLine s={s} />
            <button type="button" onClick={() => setUi({ page: "handoff" })}
              className="hit ml-auto inline-flex h-9 items-center gap-0.5 rounded-full pr-2 pl-3 text-meta font-semibold text-herald-accent hover:bg-accent-tint">
              Details<ChevronRight size={16} aria-hidden />
            </button>
          </div>
        </>}
    </div>
  );
}

export function PreAlertCard({ className }: { className?: string }) {
  const s = useHerald((st) => st.snapshot);
  const [pick, setPick] = useState<string | null>(null);
  if (!s) return <Card className={cn("p-5", className)}><p className="text-critical text-text-muted">—</p></Card>;
  // A call can open several checklists (stroke and trauma after a fall, STEMI and sepsis): one card, a switcher.
  const r = s.readiness.find((x) => x.id === pick) ?? s.readiness[0];
  const toGo = r ? r.total - r.done : 0;
  return (
    <Card id="prealert" tabIndex={-1} aria-labelledby="pa-h" className={cn("outline-none", className)}>
      <CardHeader icon={ListChecks} cat="check" id="pa-h" title={r ? r.label : "Pre-alert"}
        actions={r && (r.ready ? <Badge tone="ok" icon={CircleCheck}>Ready</Badge> : <Badge tone="medium">{toGo} to go</Badge>)} />
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-5 pb-4">
        {s.readiness.length > 1 && (
          <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Open checklists">
            {s.readiness.map((x) => (
              <Button key={x.id} size="sm" role="tab" aria-selected={x.id === r?.id}
                variant={x.id === r?.id ? "primary" : "secondary"} onClick={() => setPick(x.id)}>
                {x.label} <span className="num">{x.done}/{x.total}</span>
              </Button>
            ))}
          </div>
        )}
        {r ? (
          <>
            <div className="flex items-center gap-4">
              <Ring done={r.done} total={r.total} cat="check" size={72} stroke={9} label={`${r.done} of ${r.total} captured`}>
                <span className="rounded-num text-value">{r.done}<span className="text-meta text-text-muted">/{r.total}</span></span>
              </Ring>
              <div className="min-w-0">
                <p className="rounded-num text-[1.375rem] leading-7 text-cat-check-fg">{r.ready ? "Checklist captured" : `${toGo} to capture`}</p>
                <p className="text-meta text-text-muted">{r.done} of {r.total} pre-alert items captured</p>
              </div>
            </div>
            <div className="@container"><ul className="grid grid-cols-2 gap-x-4 @max-[20rem]:grid-cols-1" aria-label="Checklist items">
              {r.items.map((i) => {
                const it = ITEM[i.state];
                return (
                  <li key={i.key} className="flex min-h-10 items-center gap-2 border-b border-border-subtle py-1.5 text-body leading-tight">
                    <it.icon size={18} strokeWidth={2.3} aria-hidden className={cn("shrink-0", it.cls)} />
                    <span className={cn("min-w-0", i.state === "done" ? "text-text-secondary" : "font-semibold text-text-primary")}>{i.label}</span>
                    <span className="sr-only">{it.word}</span>
                  </li>
                );
              })}
            </ul></div>
          </>
        ) : (
          <p className="text-body text-text-muted">No pre-alert checklist for this dispatch yet.</p>
        )}
        <EdSync s={s} />
      </div>
    </Card>
  );
}
