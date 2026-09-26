// What Herald did: one timeline of the call, newest first. Every capture (what was heard, photographed or read off
// the monitor, with what Herald took from it), every county passage it found, every update it delivered to the ED, and
// every confirmation, rejection and correction the medic made. Before this, the tab showed a short activity summary
// and then the same captures again as a transcript, and the medic's own actions were recorded nowhere visible.
import { AudioLines, BookOpenCheck, CircleCheck, CircleX, PencilLine, Send, ShieldCheck } from "lucide-react";
import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { activity, setAside } from "@/lib/copilot";
import { useContract, label } from "@/lib/contract";
import { factValue, hhmm } from "@/lib/format";
import type { FactView, Snapshot, TranscriptEntry } from "@/lib/types";
import { useHerald } from "@/lib/store";
import { cn } from "@/lib/utils";
import { Card, EmptyState, PageHeader } from "@/components/kit";
import { TraceEntry } from "@/features/trace/trace";

type Kind = "capture" | "found" | "sent" | "checked" | "you";
interface Item { id: string; ts: string; kind: Kind; capture?: TranscriptEntry; text?: string; detail?: string; icon?: typeof Send; tone?: "ok" | "muted" }
type Filter = "all" | "captures" | "system" | "you";
const FILTERS: [Filter, string][] = [["all", "Everything"], ["captures", "Heard & seen"], ["system", "Found & sent"], ["you", "Your actions"]];
const IN: Record<Filter, (k: Kind) => boolean> = {
  all: () => true, captures: (k) => k === "capture", system: (k) => k === "found" || k === "sent" || k === "checked", you: (k) => k === "you",
};

/** The medic's own decisions, from the audit log. A bulk confirm (one tap, many facts) is one line, not nine. */
function medicActions(s: Snapshot, label: (k: string) => string): Item[] {
  const byId = new Map<string, FactView>();
  for (const f of [...s.timeline, ...Object.values(s.facts), ...Object.values(s.events ?? {}).flat()]) byId.set(f.id, f);
  const groups = new Map<string, { at: string; to: string; names: string[] }>();
  for (const e of s.audit ?? []) {
    if (e.action !== "fact_status_changed" || e.actor !== "medic" || e.from === e.to) continue;
    const f = byId.get(e.fact_id);
    const name = f ? `${f.label} ${factValue(f)}` : label(e.key);
    const key = `${e.at.slice(0, 19)}:${e.to}`;           // same second, same decision: one tap
    const g = groups.get(key) ?? { at: e.at, to: e.to, names: [] };
    g.names.push(name); groups.set(key, g);
  }
  return [...groups.entries()].map(([key, g]) => {
    const verb = g.to === "confirmed" ? "confirmed" : g.to === "rejected" ? "rejected" : `set to ${g.to}`;
    const shown = g.names.slice(0, 3).join(", ") + (g.names.length > 3 ? ` +${g.names.length - 3} more` : "");
    return { id: `you:${key}`, ts: g.at, kind: "you" as const, icon: g.to === "rejected" ? CircleX : g.to === "confirmed" ? CircleCheck : PencilLine,
      tone: g.to === "confirmed" ? "ok" as const : "muted" as const,
      text: g.names.length > 1 ? `You ${verb} ${g.names.length} facts` : `You ${verb} ${g.names[0]}`, detail: g.names.length > 1 ? shown : undefined };
  });
}

function items(s: Snapshot, label: (k: string) => string): Item[] {
  const out: Item[] = s.transcripts.map((t) => ({ id: `t:${t.id}`, ts: t.ts, kind: "capture", capture: t }));
  // System events. Camera "read" lines are left out: the capture itself is in the list with its photo and values.
  for (const l of activity(s, 500, label)) {
    if (l.kind === "found") out.push({ id: l.id, ts: l.ts, kind: "found", text: l.text, icon: BookOpenCheck });
    if (l.kind === "sent") out.push({ id: l.id, ts: l.ts, kind: "sent", text: l.text, icon: Send, tone: "ok" });
    if (l.kind === "checked") out.push({ id: l.id, ts: l.ts, kind: "checked", text: l.text, icon: ShieldCheck });
  }
  out.push(...medicActions(s, label));
  return out.sort((a, b) => b.ts.localeCompare(a.ts));
}

function EventRow({ it, ruled }: { it: Item; ruled: boolean }) {
  const Icon = it.icon ?? AudioLines;
  return <li className="flex gap-3 pl-5" data-kind={it.kind}>
    <span className={cn("mt-3 grid size-[30px] shrink-0 place-items-center rounded-lg bg-surface-2", it.tone === "ok" ? "text-ok-fg" : "text-text-muted")}><Icon size={16} aria-hidden /></span>
    <div className={cn("min-w-0 flex-1 border-border-subtle py-3 pr-5", ruled && "border-t")}>
      <p className="flex items-baseline gap-3 text-body"><span className="min-w-0 flex-1 font-medium">{it.text}</span>
        <time className="num shrink-0 text-meta text-text-muted">{hhmm(it.ts)}</time></p>
      {it.detail && <p className="mt-0.5 text-meta text-text-muted">{it.detail}</p>}
    </div>
  </li>;
}

export function TranscriptPage({ onReview }: { onReview?: () => void } = {}) {
  const patient = useHerald((s) => s.snapshot?.active_patient ?? s.snapshot?.incident.id);
  return <Timeline key={patient} onReview={onReview} />;
}

function Timeline({ onReview }: { onReview?: () => void }) {
  const s = useHerald((st) => st.snapshot);
  const concise = useHerald((st) => st.ui.mode === "medic");
  const contract = useContract();
  const [filter, setFilter] = useState<Filter>("all");
  const all = useMemo(() => (s ? items(s, (k) => { const l = label(contract, k); return l !== k ? l : k.split(".").at(-1)!.replace(/_/g, " "); }) : []), [s, contract]);
  // New CAPTURES wait behind an explicit "show latest", so the evidence being read is not pushed down mid-read; a
  // capture already shown still updates in place. The medic's own decisions and Herald's found/sent events appear at
  // once -- hiding a confirmation the medic just made would look as if it had not happened.
  const [shownIds, setShownIds] = useState<Set<string> | null>(null);
  useLayoutEffect(() => { setShownIds((prev) => prev ?? new Set(all.map((i) => i.id))); }, [all]);
  const top = useRef<HTMLDivElement>(null);
  if (!s) return null;
  const held = (i: Item) => i.kind === "capture" && !!shownIds && !shownIds.has(i.id);
  const visible = all.filter((i) => !held(i));
  const fresh = all.filter(held);
  const freshWord = `new capture${fresh.length === 1 ? "" : "s"}`;
  const shown = visible.filter((i) => IN[filter](i.kind));
  const counts = Object.fromEntries(FILTERS.map(([f]) => [f, visible.filter((i) => IN[f](i.kind)).length])) as Record<Filter, number>;
  const aside = setAside(s);
  return (
    <div ref={top} tabIndex={-1} className="flex flex-col gap-4 px-6 pt-5 pb-6">
      <PageHeader title="What Herald did" description="Everything Herald heard, saw, found and sent on this call, and every decision you made. Newest first." />
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Show">
        {FILTERS.map(([f, name]) => <button key={f} type="button" aria-pressed={filter === f} onClick={() => setFilter(f)}
          className={cn("min-h-12 rounded-full border px-4 text-body font-semibold", filter === f ? "border-herald-accent bg-accent-tint text-herald-accent" : "border-border-subtle text-text-secondary hover:bg-surface-2")}>
          {name} <span className="num text-meta font-medium text-text-muted">{counts[f]}</span></button>)}
        {aside > 0 && <span className="text-meta text-text-muted">· {aside} {aside === 1 ? "remark" : "remarks"} with nothing clinical set aside</span>}
      </div>
      <div aria-live="polite">
        {fresh.length > 0 && <button className="min-h-12 rounded-lg bg-accent-tint px-3 text-body font-semibold text-herald-accent" onClick={() => {
          setShownIds(new Set(all.map((i) => i.id))); top.current?.focus({ preventScroll: true }); top.current?.scrollIntoView({ block: "start" });
        }}>{fresh.length} {freshWord} · show latest</button>}
      </div>
      <Card>
        {shown.length === 0
          ? <EmptyState icon={AudioLines} cat="speech" title={visible.length ? "Nothing of this kind yet" : "Nothing yet"}>
              {visible.length ? "Choose Everything to see the whole call." : "What Herald hears, sees, finds and sends appears here, with every confirmation you make."}</EmptyState>
          : <ul className="py-1">{shown.map((it, i) => it.capture
              ? <li key={it.id} data-kind="capture"><TraceEntry t={it.capture} wide concise={concise} onReview={onReview} ruled={i > 0} /></li>
              : <EventRow key={it.id} it={it} ruled={i > 0} />)}</ul>}
      </Card>
    </div>
  );
}
