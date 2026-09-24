// What Herald heard and what it did with it (UX_PLAN §3.1.10): the one-line summary used by the bottom bar, and the
// trace entries used by the explain-mode panel and the Transcript page, until the Herald-thinking panel (U6).
import { Camera, Cpu, Keyboard, ListChecks, Mic, Monitor } from "lucide-react";
import { formatValue, hhmm } from "@/lib/format";
import type { TranscriptEntry } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/kit";

export function summarize(t: TranscriptEntry): string {
  const facts = [...t.trace.rules.facts, ...(t.trace.model.facts ?? [])];
  const tap = facts.filter((f) => f.status === "unconfirmed").length;
  const bits = [`${facts.length} fact${facts.length === 1 ? "" : "s"}`];
  if (tap) bits.push(`${tap} need${tap === 1 ? "s" : ""} your tap`);
  if (t.trace.effects.alerts_new.some((a) => a.type === "contradiction")) bits.push("sources disagree · held");
  for (const r of t.trace.effects.readiness) bits.push(`${r.label} ${r.from} → ${r.to} of ${r.total}`);
  if (t.trace.model.status === "running") bits.push("checking with the local model…");
  if (t.trace.model.status === "unavailable") bits.push("extraction model not running: words kept, nothing extracted");
  return bits.join(" · ");
}

export const sourceIcon = (t?: TranscriptEntry) =>
  !t ? Mic : t.captured_by === "camera" ? Camera : t.captured_by === "device" ? Monitor : t.audio_id ? Mic : Keyboard;

/** One captured utterance or photo, with the model step (or the monitor readings) and what changed on the screen. */
export function TraceEntry({ t, wide = false }: { t: TranscriptEntry; wide?: boolean }) {
  const Icon = sourceIcon(t);
  const m = t.trace.model;
  const facts = [...t.trace.rules.facts, ...(m.facts ?? [])];
  return (
    <article className={cn("flex gap-3 border-b border-border-subtle py-3.5 last:border-0", wide ? "px-5" : "px-4")}>
      <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full bg-surface-2 text-text-muted" aria-hidden><Icon size={15} /></span>
      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-2 text-meta text-text-muted">
          <span className="font-semibold text-text-secondary">{t.speaker ?? t.captured_by}</span><span className="num">{hhmm(t.ts)}</span>
        </p>
        <p className="mt-0.5 text-body font-medium">“{t.text}”</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {/* trace.rules only carries monitor/device readings now; speech and photos come from the model */}
          {t.trace.heard.source === "structured" && <Badge icon={Monitor}>Monitor · {t.trace.rules.facts.length}</Badge>}
          <Badge icon={Cpu} tone={m.status === "done" ? "accent" : m.status === "error" || m.status === "unavailable" ? "low" : "neutral"}>
            Model · {m.status}{m.ms ? <> · <span className="num">{m.ms} ms</span></> : null}
          </Badge>
          {t.trace.effects.readiness.map((r) => <Badge key={r.label} icon={ListChecks} tone={r.ready ? "ok" : "neutral"}>{r.label} {r.from} → {r.to}/{r.total}</Badge>)}
        </div>
        {wide && facts.length > 0 && (
          <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-meta text-text-secondary">
            {facts.map((f) => (
              <li key={f.id}><span className="text-text-muted">{f.label}</span> {formatValue(f.value)}{f.status === "unconfirmed" && <span className="text-medium-fg"> · needs tap</span>}</li>
            ))}
          </ul>
        )}
        <p className="mt-1.5 text-meta text-text-muted">{summarize(t)}</p>
      </div>
    </article>
  );
}
