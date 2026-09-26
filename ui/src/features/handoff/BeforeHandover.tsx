// What is left before the hand over: facts nobody confirmed, sources that disagree, and required items not recorded.
// Every row is one decision with the same controls as Needs you. None of it blocks the hand over.
import { CircleDashed, ListChecks, Undo2 } from "lucide-react";
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

export function BeforeHandover({ s, report, onReport, onNotes }: {
  s: Snapshot; report: HandoffReportData | null; onReport: (r: HandoffReportData) => void; onNotes: () => void;
}) {
  const a = useAttention();
  if (!a) return null;
  const obtained = new Set(s.incident.not_obtained ?? []);
  const missing = (report?.not_yet_known ?? []).filter((m) => !obtained.has(m.key));
  const notObtained = report?.not_obtained ?? [];
  const confirmN = readingCards(s).length + a.confirmAlerts.length + a.confirmFacts.length;
  const left = leftoverCount(s, a, missing);
  if (!left && !notObtained.length) return null;
  return <Card aria-labelledby="before-h" className="before-handover">
    <CardHeader icon={ListChecks} cat="attention" title="Before you hand over" id="before-h" />
    <p className="before-handover-count" role="status">{left
      ? <><strong>{left} {left === 1 ? "item" : "items"} left</strong> — you can hand over anyway</>
      : "Nothing left to decide"}</p>
    {a.choose.length > 0 && <Section title="Sources disagree · pick one" count={a.choose.length}>
      <ul>{a.choose.map((al) => <ContradictionRow key={alertKey(al)} a={al as Contradiction} s={s} />)}</ul>
    </Section>}
    {confirmN > 0 && <Section title="Not confirmed · stays out of the report" count={confirmN}>
      <ul><ConfirmRows s={s} a={a} /></ul>
    </Section>}
    {missing.length > 0 && <Section title="Required, not recorded" count={missing.length}>
      <ul>{missing.map((m) => <MissingRow key={m.key} item={m} onReport={onReport} onNotes={onNotes} />)}</ul>
    </Section>}
    {notObtained.length > 0 && <Section title="Unable to obtain" count={notObtained.length}>
      <ul>{notObtained.map((m) => <NotObtainedRow key={m.key} item={m} onReport={onReport} />)}</ul>
    </Section>}
  </Card>;
}
