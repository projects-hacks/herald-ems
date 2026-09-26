// What is left before the hand over: facts nobody confirmed, sources that disagree, and required items not recorded.
// One line counts them; the rows open under it. Every row is one decision with the same controls as Needs you. None
// of it blocks the hand over.
import { useState } from "react";
import { ChevronDown, CircleDashed, ListChecks, Undo2 } from "lucide-react";
import { ActionButton } from "@/components/ActionButton";
import { ManualEntry } from "@/components/ManualEntry";
import { Badge, Button, Card, CardHeader, Section } from "@/components/kit";
import { ConfirmRows, ContradictionRow, type Contradiction } from "@/features/attention/AttentionQueue";
import { useAttention } from "@/hooks/useAttention";
import { api } from "@/lib/api";
import { useContract } from "@/lib/contract";
import { readingCards } from "@/lib/copilot";
import { alertKey } from "@/lib/selectors";
import type { HandoffItem, HandoffReportData, Snapshot } from "@/lib/types";

const NEWS2_SUFFIX = / \(for NEWS2\)$/;

/** How many decisions are left; not-obtained items are settled, so they do not count. */
export function leftoverCount(s: Snapshot, a: { choose: unknown[]; confirmAlerts: unknown[]; confirmFacts: unknown[] }, missing: HandoffItem[]) {
  return readingCards(s).length + a.confirmAlerts.length + a.confirmFacts.length + a.choose.length + missing.length;
}

function MissingRow({ item, onReport, onNotes }: { item: HandoffItem; onReport: (r: HandoffReportData) => void; onNotes: () => void }) {
  const contract = useContract();
  const label = item.label.replace(NEWS2_SUFFIX, "");
  return <li className="leftover-row">
    <CircleDashed size={20} aria-hidden className="shrink-0 text-text-muted" />
    <span className="leftover-label">{label}</span>
    <span className="leftover-actions">
      {contract?.keys[item.key] ? <ManualEntry field={item.key} trigger="Add" triggerLabel={`Add ${label}`} />
        : <Button size="lg" aria-label={`Add ${label}`} onClick={onNotes}>Add</Button>}
      <ActionButton pendingKey={`not-obtained:${item.key}`} busyText="Saving…"
        onClick={() => void api.notObtained(item.key, true).then((r) => r && onReport(r))}>Not obtained</ActionButton>
    </span>
  </li>;
}

function NotObtainedRow({ item, onReport }: { item: HandoffItem; onReport: (r: HandoffReportData) => void }) {
  return <li className="leftover-row" data-settled>
    <span className="leftover-label">{item.label.replace(NEWS2_SUFFIX, "")} <Badge tone="neutral">unable to obtain</Badge></span>
    <span className="leftover-actions">
      <ActionButton pendingKey={`not-obtained:${item.key}`} busyText="Saving…" variant="ghost"
        onClick={() => void api.notObtained(item.key, false).then((r) => r && onReport(r))}><Undo2 size={16} aria-hidden />Undo</ActionButton>
    </span>
  </li>;
}

/** "3 need a tap, 1 conflict, 2 not recorded": what is left, by kind, in one line. */
export function leftoverSummary(n: { confirm: number; choose: number; missing: number; notObtained: number }): string {
  return [n.confirm && `${n.confirm} ${n.confirm === 1 ? "needs" : "need"} a tap`,
    n.choose && `${n.choose} ${n.choose === 1 ? "conflict" : "conflicts"}`,
    n.missing && `${n.missing} not recorded`,
    n.notObtained && `${n.notObtained} unable to obtain`].filter(Boolean).join(", ");
}

/** A compact card: one line that counts what is left, and the items under it. The items open on their own only when
 *  sources disagree (a choice the report cannot make), and then only the conflicts, so the report stays above the fold. */
export function BeforeHandover({ s, report, onReport, onNotes }: {
  s: Snapshot; report: HandoffReportData | null; onReport: (r: HandoffReportData) => void; onNotes: () => void;
}) {
  const a = useAttention();
  const [expanded, setExpanded] = useState<boolean | null>(null);   // null: follow whether sources disagree
  if (!a) return null;
  const obtained = new Set(s.incident.not_obtained ?? []);
  const missing = (report?.not_yet_known ?? []).filter((m) => !obtained.has(m.key));
  const notObtained = report?.not_obtained ?? [];
  const confirmN = readingCards(s).length + a.confirmAlerts.length + a.confirmFacts.length;
  const left = leftoverCount(s, a, missing);
  if (!left && !notObtained.length) return null;
  // Opened because sources disagree: only the conflicts show, the rest are one tap away; opened by the medic: all.
  const open = expanded ?? a.choose.length > 0;
  const all = expanded === true || !a.choose.length;
  const rest = left - a.choose.length + notObtained.length;
  const summary = leftoverSummary({ confirm: confirmN, choose: a.choose.length, missing: missing.length, notObtained: notObtained.length });
  return <Card aria-labelledby="before-h" className="before-handover" data-open={open || undefined}>
    <CardHeader icon={ListChecks} cat="attention" title="Before you hand over" id="before-h" className="before-handover-head"
      subtitle={<span className="before-handover-count" role="status">{left
        ? <><strong>{left} {left === 1 ? "item" : "items"} left</strong>: {summary}. You can hand over anyway.</>
        : <>Nothing left to decide{summary ? ` (${summary})` : ""}.</>}</span>}
      actions={<Button size="lg" aria-expanded={open} aria-controls="before-items" onClick={() => setExpanded(!open)}>
        {open ? "Hide" : "Show"}<ChevronDown size={18} aria-hidden className={open ? "rotate-180" : undefined} /></Button>} />
    <div id="before-items" hidden={!open} className="before-handover-items">
      {a.choose.length > 0 && <Section title="Sources disagree · pick one" count={a.choose.length}>
        <ul>{a.choose.map((al) => <ContradictionRow key={alertKey(al)} a={al as Contradiction} s={s} />)}</ul>
      </Section>}
      {!all && rest > 0 && <div className="before-handover-more">
        <Button size="lg" aria-controls="before-items" onClick={() => setExpanded(true)}>Show the other {rest} {rest === 1 ? "item" : "items"}</Button>
      </div>}
      {all && confirmN > 0 && <Section title="Not confirmed · stays out of the report" count={confirmN}>
        <ul><ConfirmRows s={s} a={a} /></ul>
      </Section>}
      {all && missing.length > 0 && <Section title="Required, not recorded" count={missing.length}>
        <ul>{missing.map((m) => <MissingRow key={m.key} item={m} onReport={onReport} onNotes={onNotes} />)}</ul>
      </Section>}
      {all && notObtained.length > 0 && <Section title="Unable to obtain" count={notObtained.length}>
        <ul>{notObtained.map((m) => <NotObtainedRow key={m.key} item={m} onReport={onReport} />)}</ul>
      </Section>}
    </div>
  </Card>;
}
