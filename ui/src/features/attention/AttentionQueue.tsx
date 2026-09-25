// Needs attention (UX_PLAN §3.1.6 and the alert slot §3.1.8, merged into one queue): everything that waits on the
// medic, grouped in the order to handle it — urgent (HIGH), sources that disagree (choose a value), facts that need a
// tap, new findings to acknowledge — then what hasn't been captured yet. One list, so nothing hides behind "1 of N".
// New alerts are announced politely (HIGH assertively). Seen findings fold into "Seen" at the end.
import {
  Brain, Camera, ChevronDown, ChevronRight, CircleCheck, CircleDashed, Gauge, GitCompareArrows, Inbox, Keyboard, Mic,
  Monitor, OctagonAlert, ShieldAlert, Sparkles, TrendingUp, type LucideIcon,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useAttention } from "@/hooks/useAttention";
import { api } from "@/lib/api";
import { factValue, formatValue, hhmm, sourceName } from "@/lib/format";
import { alertKey, alertPriority, type Priority } from "@/lib/selectors";
import { useHerald } from "@/lib/store";
import type { Alert, FactView, NeedItem, Snapshot } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ActionButton, ActionNote, usePendingAction } from "@/components/ActionButton";
import { AudioEvidence } from "@/components/AudioEvidence";
import { activeSync } from "@/lib/selectors";
import { Badge, Button, Card, CardHeader, Count, EmptyState, IconBadge, Section, type Tone } from "@/components/kit";

const NEWS2_SUFFIX = / \(for NEWS2\)$/;
type Contradiction = Extract<Alert, { type: "contradiction" }>;
type CodeStatus = Extract<Alert, { type: "confirm_required" }>;

// ---------- one row ----------

function Row({ icon, tone, title, badge, value, was, meta, actions, urgent, flash, children }: {
  icon: LucideIcon; tone: Tone; title: React.ReactNode; badge?: React.ReactNode; value?: React.ReactNode; was?: string;
  meta?: React.ReactNode; actions?: React.ReactNode; urgent?: boolean; flash?: boolean; children?: React.ReactNode;
}) {
  return (
    <li className={cn("flex flex-wrap items-start gap-x-3 gap-y-2 px-5 py-3.5", urgent && "bg-high-tint")}>
      <IconBadge icon={icon} tone={tone} iconClassName={flash ? "flash-high" : undefined} />
      <div className="min-w-0 flex-1 basis-64">
        <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-body">
          <span className="font-semibold text-text-primary">{title}</span>{badge}
        </p>
        {value !== undefined && (
          <p className="mt-0.5 text-critical font-semibold leading-snug">
            {value}{was && <span className="ml-2 text-body font-normal text-text-muted">was {was}</span>}
          </p>
        )}
        {meta && <p className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-meta text-text-muted">{meta}</p>}
        {children}
      </div>
      {actions && <div className="ml-auto flex shrink-0 items-center gap-2 self-center">{actions}</div>}
    </li>
  );
}

function PriorityBadge({ p }: { p: Priority }) {
  return p === "high" ? <Badge tone="high" variant="solid" icon={OctagonAlert} className="label-caps text-[0.6875rem]">High</Badge>
    : p === "medium" ? <Badge tone="medium" className="label-caps text-[0.6875rem]">Check</Badge>
    : <Badge tone="low" className="label-caps text-[0.6875rem]">Info</Badge>;
}

function sourceIconOf(f: FactView): LucideIcon {
  return f.captured_by === "camera" ? Camera : f.captured_by === "device" ? Monitor : f.provenance.audio_id ? Mic : Keyboard;
}

function FactMeta({ f }: { f: FactView }) {
  const Icon = sourceIconOf(f);
  const byModel = f.provenance.extractor?.startsWith("llm:");
  return (
    <>
      <Icon size={13} aria-hidden />
      <span>{f.captured_by === "camera" ? `photo${f.speaker ? ` · ${f.speaker}` : ""}` : sourceName(f)}</span>
      <span aria-hidden>·</span><span className="num">{hhmm(f.ts)}</span>
      {byModel && <><span aria-hidden>·</span><span className="inline-flex items-center gap-1 text-herald-accent"><Sparkles size={12} aria-hidden />local model</span></>}
      {f.provenance.hold_reason && <><span aria-hidden>·</span><span>{f.provenance.hold_reason}</span></>}
      <AudioEvidence id={f.provenance.audio_id} />
    </>
  );
}

// ---------- the kinds of rows ----------

function ConfirmActions({ id }: { id: string }) {
  return (
    <>
      <ActionButton pendingKey={`confirm:${id}`} onClick={() => api.confirm(id)} busyText="Saving…" variant="primary">Confirm</ActionButton>
      <ActionButton pendingKey={`reject:${id}`} onClick={() => api.reject(id)} busyText="Saving…">Reject</ActionButton>
    </>
  );
}

function TapRow({ f }: { f: FactView }) {
  return (
    <Row icon={f.provenance.extractor?.startsWith("llm:") ? Sparkles : sourceIconOf(f)} tone="accent" title={f.label} value={factValue(f)}
      was={f.previous_value !== null && f.previous_value !== undefined ? factValue({ value: f.previous_value, unit: f.unit }) : undefined}
      meta={<FactMeta f={f} />} actions={<ConfirmActions id={f.id} />} />
  );
}

function CodeStatusRow({ a }: { a: CodeStatus }) {
  const f = a.facts[0];
  return (
    <Row icon={ShieldAlert} tone="medium" title={a.label} badge={<PriorityBadge p="medium" />} value={f ? factValue(f) : undefined}
      meta={<>{f && <FactMeta f={f} />}<span aria-hidden>·</span><span>never sent until you confirm</span></>}
      actions={<ConfirmActions id={a.confirm_fact_id} />} />
  );
}

/** One choice of a disagreement: a large button with the source, the value and "Use this". Using the older value
 *  rejects the newer one; using the newer value confirms it (§3.1.8). */
function Choice({ f, a, sentToEd }: { f: FactView; a: Contradiction; sentToEd: boolean }) {
  const isNewer = f.id === a.confirm_fact_id;
  const key = `${isNewer ? "confirm" : "reject"}:${a.confirm_fact_id}`;
  const p = usePendingAction(key);
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <button type="button" disabled={p.disabled} title={p.replay ? "Replay: actions are off" : undefined}
        onClick={() => (isNewer ? api.confirm(a.confirm_fact_id) : api.reject(a.confirm_fact_id))}
        aria-label={`Use ${factValue(f)}, from ${sourceName(f)}`}
        className="group flex min-h-20 w-full flex-col gap-0.5 rounded-[12px] border border-border-subtle bg-surface-2 px-3.5 py-2.5 text-left transition-colors duration-[var(--dur-short3)] enabled:hover:border-herald-accent disabled:cursor-not-allowed">
        <span className="flex w-full flex-wrap items-center gap-x-2 gap-y-1 text-meta text-text-muted">
          <span className="font-semibold text-text-secondary">{sourceName(f)}</span><span className="num">{hhmm(f.ts)}</span>
          <span className="ml-auto">{isNewer ? <Badge tone="medium">new · held</Badge> : sentToEd ? <Badge tone="ok">ED has this</Badge> : <Badge>earlier</Badge>}</span>
        </span>
        <span className="text-critical font-semibold">{factValue(f)}</span>
        <span className={cn("text-meta font-semibold", p.disabled ? "text-text-muted" : "text-herald-accent")}>{p.busy ? "Saving…" : "Use this"}</span>
      </button>
      <ActionNote a={p} />
    </div>
  );
}

function ContradictionRow({ a, s }: { a: Contradiction; s: Snapshot }) {
  const [older, newer] = a.facts;
  const sentToEd = older?.status === "confirmed" && activeSync(s)[a.key] === "sent";
  return (
    <Row icon={GitCompareArrows} tone="medium" title={<>{a.label}: sources disagree</>} badge={<PriorityBadge p="medium" />}
      meta={sentToEd && newer
        ? <span>The ED has “{factValue(older)}”. “{factValue(newer)}” stays on the vehicle until you choose.</span>
        : <span>Neither value leaves the vehicle until you choose.</span>}>
      {older && newer && (
        <div className="mt-2.5 grid grid-cols-2 gap-2.5 max-sm:grid-cols-1">
          {a.facts.map((f) => <Choice key={f.id} f={f} a={a} sentToEd={sentToEd} />)}
        </div>
      )}
    </Row>
  );
}

function FindingRow({ a, s, onSeen }: { a: Alert; s: Snapshot; onSeen?: () => void }) {
  const p = alertPriority(a);
  const tone: Tone = p === "high" ? "high" : p === "medium" ? "medium" : "low";
  const seen = onSeen && <Button size="md" onClick={onSeen}>Got it</Button>;
  switch (a.type) {
    case "trauma_alert_criteria": case "sepsis_prenotification":
      return <Row icon={ShieldAlert} tone={tone} urgent={p === "high" && !!onSeen} badge={<PriorityBadge p={p} />} title={a.label} actions={seen}>
        <ul className="mt-2 space-y-2 text-body">{a.criteria.map((line, i) => <li key={i}>{line}</li>)}</ul>
        {a.county_rule?.map((line, i) => <p key={i} className="mt-2 text-body">{a.county && <span>{a.county}: </span>}{line}</p>)}
      </Row>;
    case "news2_rise": {
      const parts = Object.entries(s.scores.news2.parts).filter(([, v]) => v.points > 0).map(([k, v]) => `${k} ${formatValue(v.value)} (+${v.points})`);
      return <Row icon={Gauge} tone={tone} urgent={p === "high" && !!onSeen} flash={p === "high" && !!onSeen} badge={<PriorityBadge p={p} />}
        title={<>NEWS2 rose <span className="num">{a.from} → {a.to}</span> · {a.band} band</>} meta={parts.length ? <span>{parts.join(" · ")}</span> : undefined} actions={seen} />;
    }
    case "race_positive":
      return <Row icon={Brain} tone={tone} badge={<PriorityBadge p={p} />} title={<>RACE <span className="num">{a.score}</span> of 9: large-vessel screen positive</>}
        meta={<span>Threshold ≥ 5. Parts and published accuracy are on the RACE tile.</span>} actions={seen} />;
    case "gfast_positive":
      return <Row icon={Brain} tone={tone} badge={<PriorityBadge p={p} />} title={<>G.F.A.S.T. <span className="num">{a.score}</span> of 4: screen positive</>}
        meta={<span>{a.county_rule}</span>} actions={seen} />;
    case "significant_change": {
      const d = a.series[a.series.length - 1] - a.series[0];
      return <Row icon={TrendingUp} tone={tone} badge={<PriorityBadge p={p} />} title={<>{a.label} changed <span className="num">{a.series.join(" → ")}</span></>}
        meta={<span className="num">{d > 0 ? "+" : ""}{d} since the first reading</span>} actions={seen} />;
    }
    default:
      return null;
  }
}

// ---------- what hasn't been captured ----------

function Chips({ items }: { items: NeedItem[] }) {
  return (
    <ul className="flex flex-wrap gap-2">
      {items.map((m) => (
        <li key={m.key} className="inline-flex min-h-9 items-center gap-1.5 rounded-full border border-dashed border-border-control px-3 text-body font-medium">
          <CircleDashed size={15} aria-hidden className="text-text-muted" />{m.label.replace(NEWS2_SUFFIX, "")}
          {m.pending_confirm && <span className="text-meta font-normal text-text-muted">· awaiting tap</span>}
        </li>
      ))}
    </ul>
  );
}

function StillToCapture({ s }: { s: Snapshot }) {
  const checklist = new Set(s.readiness.flatMap((r) => r.items.map((i) => i.key)));
  const gaps = s.needs_attention.missing.filter((m) => checklist.has(m.key));
  const news2 = s.needs_attention.missing.filter((m) => !checklist.has(m.key));
  const unknown = s.needs_attention.unknown;
  if (!gaps.length && !news2.length && !unknown.length) return null;
  return (
    <Section title="Still to capture" count={gaps.length + unknown.length + news2.length}>
      <div className="flex flex-col gap-3 px-5 pt-1 pb-4">
        {gaps.length > 0 && <div className="flex flex-col gap-1.5"><p className="text-meta text-text-muted">{s.readiness[0]?.label ?? "Pre-alert"} checklist</p><Chips items={gaps} /></div>}
        {unknown.length > 0 && <div className="flex flex-col gap-1.5"><p className="text-meta text-text-muted">Not asked yet</p><Chips items={unknown} /></div>}
        {news2.length > 0 && (
          <p className="text-body text-text-secondary"><span className="font-semibold text-text-primary">NEWS2 still needs </span>{news2.map((m) => m.label.replace(NEWS2_SUFFIX, "")).join(" · ")}</p>
        )}
      </div>
    </Section>
  );
}

// ---------- the card ----------

export function AttentionQueue({ className }: { className?: string }) {
  const s = useHerald((st) => st.snapshot);
  const markSeen = useHerald((st) => st.markSeen);
  const a = useAttention();
  const [showSeen, setShowSeen] = useState(false);
  const known = useRef<Set<string>>(new Set());
  const live = useRef<HTMLDivElement>(null);
  const liveHigh = useRef<HTMLDivElement>(null);

  useEffect(() => {   // announce each alert once, when it is shown (not while push-to-talk holds it back)
    for (const al of a ? [...a.urgent, ...a.choose, ...a.confirmAlerts, ...a.review] : []) {
      const k = alertKey(al);
      if (known.current.has(k)) continue;
      known.current.add(k);
      const region = alertPriority(al) === "high" ? liveHigh.current : live.current;
      if (region) region.textContent = `New: ${al.label}`;
    }
  }, [a]);

  const confirmCount = a ? a.confirmAlerts.length + a.confirmFacts.length : 0;
  return (
    <Card id="needs-attention" tabIndex={-1} aria-labelledby="na-h" className={cn("outline-none", className)}>
      <CardHeader icon={Inbox} tone={a?.urgent.length ? "high" : a?.count ? "medium" : "ok"} title="Needs attention" id="na-h"
        badge={a && a.count > 0 ? <Count n={a.count} tone={a.urgent.length ? "high" : "medium"} /> : undefined}
        subtitle="Nothing unconfirmed leaves the vehicle." />
      <div className="min-h-0 flex-1 overflow-y-auto border-t border-border-subtle pb-2">
        {!s || !a ? <p className="px-5 py-4 text-critical text-text-muted">—</p> : <>
          {a.count === 0 && (
            <EmptyState icon={CircleCheck} title="Nothing to confirm" className="py-5">
              Anything Herald needs you to confirm, choose or acknowledge shows up here.
            </EmptyState>
          )}
          {a.urgent.length > 0 && (
            <Section title="Urgent" count={a.urgent.length} tone="high">
              <ul className="divide-y divide-border-subtle">{a.urgent.map((al) => <FindingRow key={alertKey(al)} a={al} s={s} onSeen={() => markSeen(alertKey(al))} />)}</ul>
            </Section>
          )}
          {a.choose.length > 0 && (
            <Section title="Choose a value" count={a.choose.length} tone="medium">
              <ul className="divide-y divide-border-subtle">{a.choose.map((al) => <ContradictionRow key={alertKey(al)} a={al as Contradiction} s={s} />)}</ul>
            </Section>
          )}
          {confirmCount > 0 && (
            <Section title="Needs your tap" count={confirmCount} tone="accent">
              <ul className="divide-y divide-border-subtle">
                {a.confirmAlerts.map((al) => <CodeStatusRow key={alertKey(al)} a={al as CodeStatus} />)}
                {a.confirmFacts.map((f) => <TapRow key={f.id} f={f} />)}
              </ul>
            </Section>
          )}
          {a.review.length > 0 && (
            <Section title="New findings" count={a.review.length} tone="medium"
              actions={a.review.length > 1 && <Button size="sm" variant="ghost" onClick={() => markSeen(...a.review.map(alertKey))}>Mark all seen</Button>}>
              <ul className="divide-y divide-border-subtle">{a.review.map((al) => <FindingRow key={alertKey(al)} a={al} s={s} onSeen={() => markSeen(alertKey(al))} />)}</ul>
            </Section>
          )}
          <StillToCapture s={s} />
          {a.acknowledged.length > 0 && (
            <div className="px-5 pt-1">
              <button type="button" onClick={() => setShowSeen(!showSeen)} aria-expanded={showSeen}
                className="inline-flex min-h-10 items-center gap-1.5 text-meta font-semibold text-text-muted hover:text-text-primary">
                {showSeen ? <ChevronDown size={15} aria-hidden /> : <ChevronRight size={15} aria-hidden />}Seen · {a.acknowledged.length}
              </button>
              {showSeen && <ul className="-mx-5 divide-y divide-border-subtle opacity-75">{a.acknowledged.map((al) => <FindingRow key={alertKey(al)} a={al} s={s} />)}</ul>}
            </div>
          )}
        </>}
      </div>
      <div ref={live} aria-live="polite" className="sr-only" />
      <div ref={liveHigh} aria-live="assertive" className="sr-only" />
    </Card>
  );
}
