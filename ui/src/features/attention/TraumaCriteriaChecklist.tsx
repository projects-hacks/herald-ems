// Trauma/field-triage criteria as a tappable checklist, not a report of what speech happened to catch.
// Speech extraction of trauma.criteria measures ~0.2 recall on every model tried (docs/MODEL_PLAN.md bake-off):
// most injury patterns and mechanisms a medic actually observed are never heard. Rendering only the criteria the
// model caught would make the panel look like a complete automatic screen when it is closer to a coin flip per
// criterion. So every criterion the county lists is shown; the ones a plain "value described" rule can record
// (herald/api/contract.py's `_tap`) are one tap to add and one more to confirm — the same two-step every manual
// entry in this app already requires, never a shortcut around it. Vitals, medications and recorded procedures
// have their own capture flow and stay read-only here.
import { CircleCheck, CircleDashed, ShieldAlert } from "lucide-react";
import { useContract } from "@/lib/contract";
import { traumaCriteriaRows, type TraumaCriterionRow } from "@/lib/selectors";
import { api } from "@/lib/api";
import type { Alert, Snapshot } from "@/lib/types";
import { ActionButton } from "@/components/ActionButton";
import { Badge } from "@/components/kit";

type TraumaAlert = Extract<Alert, { type: "trauma_alert_criteria" }>;

function Row({ row }: { row: TraumaCriterionRow }) {
  const code = row.code ? <span className="num text-text-muted">{row.code}</span> : null;
  if (row.status === "confirmed") {
    return <li className="flex min-h-12 items-center gap-2 py-1.5 text-body">
      <CircleCheck size={17} className="shrink-0 text-ok-fg" aria-label="confirmed" />{code}<span>{row.label}</span>
    </li>;
  }
  if (row.status === "unconfirmed" && row.factId) {
    return <li className="flex min-h-12 flex-wrap items-center gap-2 py-1.5 text-body">
      <CircleDashed size={17} className="shrink-0 text-medium-fg" aria-hidden />{code}<span className="flex-1">{row.label}</span>
      <span className="text-meta text-text-muted">heard, not confirmed</span>
      <ActionButton pendingKey={`confirm:${row.factId}`} onClick={() => api.confirm(row.factId!)} busyText="Confirming…" size="md">Confirm</ActionButton>
    </li>;
  }
  if (row.status === "unmarked" && row.tap) {
    const tap = row.tap;
    return <li className="flex min-h-12 flex-wrap items-center gap-2 py-1.5 text-body">
      <CircleDashed size={17} className="shrink-0 text-text-muted" aria-hidden />{code}<span className="flex-1">{row.label}</span>
      <ActionButton pendingKey={`mark:${tap.key}:${tap.value}`} onClick={() => api.markCriterion(tap.key, tap.value)} busyText="Marking…" size="md">Mark</ActionButton>
    </li>;
  }
  // "computed": vitals/medication/procedure criteria — no tap target, sourced from their own capture flow.
  const met = row.computedState === "met";
  return <li className="flex min-h-12 items-center gap-2 py-1.5 text-body text-text-secondary">
    {met ? <CircleCheck size={17} className="shrink-0 text-ok-fg" aria-label="met" /> : <CircleDashed size={17} className="shrink-0 text-text-muted" aria-hidden />}
    {code}<span>{row.label}</span>{!met && <span className="text-meta text-text-muted">from vitals/meds, not here</span>}
  </li>;
}

/** For trauma/fall dispatches only: this alert type is itself gated on the trauma checklist opening on a trauma
 * mechanism trigger (config/checklists.yaml), so nothing further to gate here. */
export function TraumaCriteriaChecklist({ a, s }: { a: TraumaAlert; s: Snapshot }) {
  const contract = useContract();
  const rows = traumaCriteriaRows(s, contract?.scores?.[a.score]?.criteria, a.score);
  const confirmedCount = rows.filter((r) => r.status === "confirmed" || (r.status === "computed" && r.computedState === "met")).length;
  const byGroup = new Map<string, TraumaCriterionRow[]>();
  for (const r of rows) byGroup.set(r.group, [...(byGroup.get(r.group) ?? []), r]);
  const groupLabel = (id: string) => contract?.scores?.[a.score]?.groups?.find((g) => g.id === id)?.label ?? id;
  if (!rows.length) {
    // The contract hasn't loaded yet, or this score has no per-criterion breakdown; fall back to the alert's
    // own already-met list rather than showing nothing.
    return <ul className="mt-2 space-y-2 text-body">{a.criteria.map((line, i) => <li key={i}>{line}</li>)}</ul>;
  }
  return <div className="mt-2">
    <p className="flex flex-wrap items-center gap-2 text-body font-semibold">
      <ShieldAlert size={16} className="shrink-0 text-medium-fg" aria-hidden />
      Based on {confirmedCount} confirmed criteri{confirmedCount === 1 ? "on" : "a"} — not a complete screen
      <Badge tone="medium">speech misses most criteria</Badge>
    </p>
    <p className="mt-1 text-meta text-text-muted">Every county criterion is listed. Tap one you observe that speech didn't catch; heard-but-unconfirmed criteria need one more tap.</p>
    {[...byGroup.entries()].map(([group, groupRows]) => (
      <div key={group} className="mt-3">
        <p className="text-meta font-semibold text-text-muted">{groupLabel(group)}</p>
        <ul>{groupRows.map((row) => <Row key={row.code ?? row.label} row={row} />)}</ul>
      </div>
    ))}
  </div>;
}
