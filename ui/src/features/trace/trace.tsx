// What Herald heard and what it did with it: the one-line summary used by the bottom bar, and the
// trace entries used by the explain-mode panel and the Transcript page, until the Herald-thinking panel (U6).
import { Camera, Cpu, Keyboard, ListChecks, Mic, Monitor } from "lucide-react";
import { formatValue, hhmm } from "@/lib/format";
import type { TranscriptEntry } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Badge, IconTile } from "@/components/kit";
import { AudioEvidence } from "@/components/AudioEvidence";
import { useHerald } from "@/lib/store";
import { ActionButton } from "@/components/ActionButton";
import { api } from "@/lib/api";

export function summarize(t: TranscriptEntry): string {
  const facts = [...t.trace.rules.facts, ...(t.trace.model.facts ?? [])];
  const tap = facts.filter((f) => f.status === "unconfirmed").length;
  const bits = [`${facts.length} fact${facts.length === 1 ? "" : "s"}`];
  if (tap) bits.push(`${tap} need${tap === 1 ? "s" : ""} your tap`);
  if (t.trace.effects.alerts_new.some((a) => a.type === "contradiction")) bits.push("sources disagree · held");
  for (const r of t.trace.effects.readiness) bits.push(`${r.label} ${r.from} → ${r.to} of ${r.total}`);
  if (t.trace.model.status === "running") bits.push("Processing captured information…");
  if (t.trace.model.status === "unavailable") bits.push("Extraction unavailable — captured words retained, no new facts extracted");
  if (t.trace.model.status === "error") bits.push("Could not extract facts — review this capture");
  if (t.stt?.error) bits.push("speech-to-text failed; recording retained for review");
  return bits.join(" · ");
}

export const sourceIcon = (t?: TranscriptEntry) =>
  !t ? Mic : t.captured_by === "camera" ? Camera : t.captured_by === "device" ? Monitor : t.audio_id ? Mic : Keyboard;

/** One captured utterance or photo, with the model step (or the monitor readings) and what changed on the screen. */
export function TraceEntry({ t, wide = false, concise = false, onReview }: {
  t: TranscriptEntry; wide?: boolean; concise?: boolean; onReview?: () => void;
}) {
  const snapshot = useHerald((s) => s.snapshot);
  const blocked = useHerald((s) => s.source === "fixture" || s.stale || s.conn !== "open");
  const Icon = sourceIcon(t);
  const m = t.trace.model;
  const facts = [...t.trace.rules.facts, ...(m.facts ?? [])];
  const eligible = facts.filter((f) => f.status === "unconfirmed" && !f.hold_reason).map((f) => f.id);
  const failed = m.status === "error" || m.status === "unavailable";
  const processing = <div className="mt-2 flex flex-wrap gap-1.5">
    {/* trace.rules carries monitor/device readings; speech and photos come from the model. */}
    {t.trace.heard.source === "structured" && <Badge icon={Monitor}>Monitor · {t.trace.rules.facts.length}</Badge>}
    <Badge icon={Cpu} tone={m.status === "done" ? "accent" : failed ? "low" : "neutral"}>
      Model · {m.status}{m.ms ? <> · <span className="num">{m.ms} ms</span></> : null}
    </Badge>
    {concise && t.trigger && <Badge>Capture trigger · {t.trigger}</Badge>}
    {t.trace.effects.readiness.map((r) => <Badge key={r.label} icon={ListChecks} tone={r.ready ? "ok" : "neutral"}>{r.label} {r.from} → {r.to}/{r.total}</Badge>)}
  </div>;
  return (
    <article className={cn("group/entry flex gap-3", wide ? "pl-5" : "pl-4")}>
      <IconTile icon={Icon} cat="speech" size={30} className="mt-3.5" />
      <div className={cn("min-w-0 flex-1 border-t border-border-subtle py-3.5 group-first/entry:border-t-0", wide ? "pr-5" : "pr-4")}>
        <p className="flex items-center gap-2 text-meta text-text-muted">
          <span className="font-semibold text-cat-speech-fg">{t.speaker ?? t.captured_by}</span><span className="num">{hhmm(t.ts)}</span>
        </p>
        <p className="mt-0.5 text-body font-medium">“{t.text}”</p>
        {t.trigger && <div className="mt-3 rounded-xl border border-border-subtle p-3">
          <p className="text-meta font-semibold">{t.trigger === "manual" ? "Show Herald" : "Automatic capture"}{!concise && <> · {t.trigger}</>}</p>
          {t.photo_id ? <a href={`/api/photo/${t.photo_id}`} target="_blank" rel="noreferrer"><img src={`/api/photo/${t.photo_id}`} alt="Stored capture evidence; open full image" className="my-2 max-h-36 rounded-lg" /></a> : <p className="text-meta text-text-muted">No image retained.</p>}
          <ul>{t.fact_ids.map((id) => {
            const fact = [...Object.values(snapshot?.facts ?? {}), ...Object.values(snapshot?.events ?? {}).flat()].find((f) => f.id === id);
            if (!fact) return null;
            return <li key={id} className="my-2 flex flex-wrap items-center gap-3 text-body"><span>{fact.label}: {formatValue(fact.value)}</span>
              {fact.verify?.status === "match" && <span className="text-meta">Label seen ✓ · ingredient only</span>}
              {fact.status === "unconfirmed" && !(fact.verify?.status === "mismatch" && !fact.verify.resolution) && <ActionButton disabled={blocked} pendingKey={`confirm:${id}`} onClick={() => api.confirm(id)} busyText="Confirming…" size="md">Confirm</ActionButton>}
              {fact.verify?.status === "mismatch" && !fact.verify.resolution && <button className="min-h-12 px-3 text-herald-accent" onClick={() => onReview ? onReview() : useHerald.getState().setUi({ page: "overview" })}>Review mismatch</button>}
            </li>;
          })}</ul>
        </div>}
        {!concise && processing}
        {eligible.length > 1 && <div className="mt-2">
          <ActionButton disabled={blocked} pendingKey={`confirm-many:${eligible.slice().sort().join(",")}`}
            onClick={() => api.confirmMany(eligible)} busyText="Confirming…" size="md">
            Confirm eligible from this capture ({eligible.length})
          </ActionButton>
        </div>}
        {m.status === "unavailable" && <div className="mt-2 flex flex-wrap items-center gap-2" role="status">
          <span className="text-body text-low-fg">Words were preserved; extraction did not run.</span>
          <ActionButton disabled={blocked} pendingKey={`retry:${t.id}`} onClick={() => api.retryTranscript(t.id)}
            busyText="Retrying…" size="md">Retry extraction</ActionButton>
        </div>}
        {t.stt?.error && <p className="mt-2 text-body text-low-fg" role="alert">
          Speech-to-text failed. The audio recording is retained for review; no transcript was created.
        </p>}
        {wide && facts.length > 0 && (
          <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-meta text-text-secondary">
            {facts.map((f) => (
              <li key={f.id}><span className="text-text-muted">{f.label}</span> {formatValue(f.value)}{f.status === "unconfirmed" && <span className="text-medium-fg"> · needs tap</span>}</li>
            ))}
          </ul>
        )}
        <AudioEvidence id={t.audio_id} />
        <p role={failed ? "alert" : m.status === "running" ? "status" : undefined}
          className={cn("mt-1.5 text-meta", failed ? "text-medium-fg" : "text-text-muted")}>{summarize(t)}</p>
        {concise && <details className="mt-2"><summary className="min-h-12 cursor-pointer py-3 text-meta text-text-secondary">Processing details</summary>{processing}</details>}
      </div>
    </article>
  );
}
