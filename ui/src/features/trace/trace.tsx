// What Herald heard and what it did with it (UX_PLAN §3.1.10): the one-line summary used by the bottom bar, and the
// trace entries used by the explain-mode panel and the Transcript page, until the Herald-thinking panel (U6).
import { Camera, Cpu, Keyboard, ListChecks, Mic, Monitor, Ruler } from "lucide-react";
import { formatValue, hhmm } from "@/lib/format";
import type { TranscriptEntry } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Badge, IconTile } from "@/components/kit";

export function summarize(t: TranscriptEntry): string {
  const facts = [...t.trace.rules.facts, ...(t.trace.model.facts ?? [])];
  const tap = facts.filter((f) => f.status === "unconfirmed").length;
  const bits = [`${facts.length} fact${facts.length === 1 ? "" : "s"}`];
  if (tap) bits.push(`${tap} need${tap === 1 ? "s" : ""} your tap`);
  if (t.trace.effects.alerts_new.some((a) => a.type === "contradiction")) bits.push("sources disagree · held");
  for (const r of t.trace.effects.readiness) bits.push(`${r.label} ${r.from} → ${r.to} of ${r.total}`);
  if (t.trace.model.status === "running") bits.push("checking with the local model…");
  return bits.join(" · ");
}

export const sourceIcon = (t?: TranscriptEntry) =>
  !t ? Mic : t.captured_by === "camera" ? Camera : t.captured_by === "device" ? Monitor : t.audio_id ? Mic : Keyboard;

/** One captured utterance or photo, with the rules and model steps and what changed on the screen. */
export function TraceEntry({ t, wide = false }: { t: TranscriptEntry; wide?: boolean }) {
  const Icon = sourceIcon(t);
  const m = t.trace.model;
  const facts = [...t.trace.rules.facts, ...(m.facts ?? [])];
  return (
    <article className={cn("group/entry flex gap-3", wide ? "pl-5" : "pl-4")}>
      <IconTile icon={Icon} cat="speech" size={30} className="mt-3.5" />
      <div className={cn("min-w-0 flex-1 border-t border-border-subtle py-3.5 group-first/entry:border-t-0", wide ? "pr-5" : "pr-4")}>
        <p className="flex items-center gap-2 text-meta text-text-muted">
          <span className="font-semibold text-cat-speech-fg">{t.speaker ?? t.captured_by}</span><span className="num">{hhmm(t.ts)}</span>
        </p>
        <p className="mt-0.5 text-body font-medium">“{t.text}”</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          <Badge icon={Ruler}>Rules · {t.trace.rules.facts.length} · <span className="num">{t.trace.rules.ms} ms</span></Badge>
          <Badge icon={Cpu} tone={m.status === "done" ? "accent" : m.status === "error" ? "low" : "neutral"} className="max-w-full">
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
