// The patient record: every current fact, grouped in the order a receiving clinician reads it (safety first), one
// compact row per fact -- label, value with its clinical severity, where it came from and when, its status, and a
// correction. Rejected facts can be restored.
import { CircleCheck, CircleQuestionMark, CircleX, UserRound } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import { GROUP_CAT } from "@/lib/categories";
import { factValue, formatValue, hhmm, sourceName } from "@/lib/format";
import { allFacts, groupFacts } from "@/lib/selectors";
import { AudioEvidence } from "@/components/AudioEvidence";
import { useHerald } from "@/lib/store";
import type { FactView } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ActionButton } from "@/components/ActionButton";
import { CorrectFactDialog } from "@/components/CorrectFactDialog";
import { MismatchCard } from "@/features/capture/MismatchCard";
import { CAT_ICON, Card, CardHeader, Count, EmptyState, PageHeader, SEVERITY, SeverityBadge, SourceIcon, TEXT } from "@/components/kit";

function FactRow({ f }: { f: FactView }) {
  if (f.verify?.status === "mismatch" && !f.verify.resolution) return <MismatchCard fact={f} />;
  const [Icon, cls, word] = f.status === "confirmed" ? [CircleCheck, "text-ok-fg", "Confirmed"]
    : f.status === "rejected" ? [CircleX, "text-text-muted", "Rejected"] : [CircleQuestionMark, "text-medium-fg", "Needs your tap"];
  const waiting = f.status === "unconfirmed";
  const sev = f.severity ? SEVERITY[f.severity] : null;
  return (
    <li className="ml-5 grid grid-cols-[minmax(0,8.5rem)_minmax(0,1fr)_auto] items-start gap-x-3 border-t border-border-subtle py-2.5 pr-3 first:border-t-0"
      data-status={f.status} aria-label={`${f.label}: ${factValue(f)}, ${word}${f.severity ? `, ${f.severity}` : ""}`}>
      {/* Labels wrap rather than truncate: "G.F.A.S.T. arm or leg weakness/drift" must be readable in a record. */}
      <span className="pt-0.5 text-meta leading-snug text-text-secondary">{f.label}</span>
      <span className="min-w-0">
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className={cn("text-body font-semibold", sev && TEXT[sev.tone])}>{factValue(f)}</span>
          {f.severity && <SeverityBadge severity={f.severity} />}
        </span>
        <span className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-meta text-text-muted">
          <SourceIcon capturedBy={f.captured_by} role={f.role} hasAudio={!!f.provenance.audio_id} />{sourceName(f)} · <span className="num">{hhmm(f.ts)}</span>
          {f.previous_value !== null && f.previous_value !== undefined && <span>· was {formatValue(f.previous_value)}</span>}
          {f.verify?.status === "match" && <span>· label seen ✓ (ingredient only)</span>}
        </span>
        <AudioEvidence id={f.provenance.audio_id} />
        {waiting && <span className="flex flex-wrap gap-2 pt-2">
          <ActionButton pendingKey={`confirm:${f.id}`} onClick={() => api.confirm(f.id)} busyText="Confirming…" size="sm">Confirm</ActionButton>
          <ActionButton pendingKey={`reject:${f.id}`} onClick={() => api.reject(f.id)} busyText="Rejecting…" size="sm">Reject</ActionButton>
        </span>}
      </span>
      <span className="flex items-center gap-1">
        <Icon size={18} className={cls} aria-label={word} />
        {f.status !== "rejected" && <CorrectFactDialog fact={f} iconOnly />}
      </span>
    </li>
  );
}

export function PatientPage() {
  const s = useHerald((st) => st.snapshot);
  const [showRejected, setShowRejected] = useState(false);
  if (!s) return null;
  const facts = allFacts(s).filter((f) => f.status !== "rejected");
  const groups = groupFacts(facts);
  const waiting = facts.filter((f) => f.status === "unconfirmed").length;
  const rejected = s.timeline.filter((f) => f.status === "rejected");
  return (
    <div className="flex flex-col gap-5 px-6 pt-5 pb-6">
      <PageHeader title="Patient" description={facts.length
        ? `${facts.length} facts${waiting ? ` · ${waiting} waiting for your tap` : " · all confirmed"}. Safety first; each with who said it and when.`
        : "Every fact Herald captures appears here, with who said it and when."} />
      {groups.length === 0 && <Card><EmptyState icon={UserRound} cat="patient" title="Nothing captured yet">Facts appear here as Herald hears them.</EmptyState></Card>}
      <div className="columns-1 gap-4 lg:columns-2 2xl:columns-3 [&>*]:mb-4 [&>*]:break-inside-avoid">
        {groups.map(([name, fs]) => {
          const cat = GROUP_CAT[name] ?? "attention";
          return (
            <Card key={name} aria-label={name} data-group={name}>
              <CardHeader icon={CAT_ICON[cat]} cat={cat} title={name} actions={<Count n={fs.length} />} className="pb-1" />
              <ul>{fs.map((f) => <FactRow key={f.id} f={f} />)}</ul>
            </Card>
          );
        })}
        {rejected.length > 0 && (
          <Card aria-label="Rejected">
            <button type="button" onClick={() => setShowRejected(!showRejected)} aria-expanded={showRejected} className="flex min-h-14 items-center gap-2 px-5 text-left text-title font-semibold text-text-secondary">
              Rejected <Count n={rejected.length} /><span className="ml-auto text-meta font-semibold text-herald-accent">{showRejected ? "Hide" : "Show"}</span>
            </button>
            {showRejected && (
              <ul>{rejected.map((f) => (
                <li key={f.id} className="ml-5 flex items-center gap-3 border-t border-border-subtle py-2 pr-5 text-body">
                  <span className="w-36 truncate text-meta text-text-muted">{f.label}</span><span className="min-w-0 flex-1 truncate">{factValue(f)}</span>
                  <ActionButton pendingKey={`confirm:${f.id}`} onClick={() => api.confirm(f.id)} busyText="Restoring…" size="md">Restore</ActionButton>
                </li>
              ))}</ul>
            )}
          </Card>
        )}
      </div>
    </div>
  );
}
