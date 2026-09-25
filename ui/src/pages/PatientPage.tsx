// Patient (UX_PLAN §3.1.9 "patient picture"): every current fact with its source and status, grouped into cards;
// rejected facts can be restored.
import { Camera, CircleCheck, CircleQuestionMark, CircleX, Keyboard, Mic, Monitor, UserRound } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import { factValue, formatValue, hhmm, sourceName } from "@/lib/format";
import { allFacts, groupFacts } from "@/lib/selectors";
import { AudioEvidence } from "@/components/AudioEvidence";
import { useHerald } from "@/lib/store";
import type { FactView } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ActionButton } from "@/components/ActionButton";
import { Card, CardHeader, Count, EmptyState, PageHeader } from "@/components/kit";

function SourceIcon({ f }: { f: FactView }) {
  const Icon = f.captured_by === "camera" ? Camera : f.captured_by === "device" ? Monitor : f.provenance.audio_id ? Mic : Keyboard;
  return <Icon size={13} aria-label={f.captured_by === "camera" ? "photo" : f.captured_by === "device" ? "monitor" : f.provenance.audio_id ? "voice" : "typed"} />;
}

function FactRow({ f }: { f: FactView }) {
  const [Icon, cls, word] = f.status === "confirmed" ? [CircleCheck, "text-ok-fg", "Confirmed"]
    : f.status === "rejected" ? [CircleX, "text-text-muted", "Rejected"] : [CircleQuestionMark, "text-medium-fg", "Needs your tap"];
  return (
    <li className="grid grid-cols-[minmax(0,9.5rem)_minmax(0,1fr)_1.25rem] items-start gap-x-3 border-b border-border-subtle px-5 py-2.5 last:border-0">
      <span className="truncate pt-px text-meta text-text-muted">{f.label}</span>
      <span className="min-w-0">
        <span className="block text-body font-semibold">{factValue(f)}</span>
        <AudioEvidence id={f.provenance.audio_id} />
        {f.status === "unconfirmed" && !(f.verify?.status === "mismatch" && !f.verify.resolution) && <span className="flex flex-wrap gap-2 py-2"><ActionButton pendingKey={`confirm:${f.id}`} onClick={() => api.confirm(f.id)} busyText="Confirming…">Confirm</ActionButton><ActionButton pendingKey={`reject:${f.id}`} onClick={() => api.reject(f.id)} busyText="Rejecting…">Reject</ActionButton></span>}
        {f.verify?.status === "match" && <span className="text-meta text-text-secondary">Label seen ✓ · ingredient only</span>}
        <span className="flex flex-wrap items-center gap-x-1.5 text-meta text-text-muted">
          <SourceIcon f={f} />{sourceName(f)} · <span className="num">{hhmm(f.ts)}</span>
          {f.previous_value !== null && f.previous_value !== undefined && <span>· was {formatValue(f.previous_value)}</span>}
        </span>
      </span>
      <Icon size={17} className={cn("mt-0.5", cls)} aria-label={word} />
    </li>
  );
}

export function PatientPage() {
  const s = useHerald((st) => st.snapshot);
  const [showRejected, setShowRejected] = useState(false);
  if (!s) return null;
  const groups = groupFacts(allFacts(s).filter((f) => f.status !== "rejected"));
  const rejected = s.timeline.filter((f) => f.status === "rejected");
  return (
    <div className="flex flex-col gap-5 p-6">
      <PageHeader title="Patient" description="Every current fact, grouped, with who said it and whether it's confirmed." />
      {groups.length === 0 && <Card><EmptyState icon={UserRound} tone="neutral" title="Nothing captured yet">Facts appear here as Herald hears them.</EmptyState></Card>}
      <div className="columns-1 gap-4 md:columns-2 2xl:columns-3 [&>*]:mb-4 [&>*]:break-inside-avoid">
        {groups.map(([name, facts]) => (
          <Card key={name} aria-label={name}>
            <CardHeader title={name} badge={<Count n={facts.length} />} className="pb-2" />
            <ul className="border-t border-border-subtle">{facts.map((f) => <FactRow key={f.id} f={f} />)}</ul>
          </Card>
        ))}
        {rejected.length > 0 && (
          <Card aria-label="Rejected">
            <button type="button" onClick={() => setShowRejected(!showRejected)} aria-expanded={showRejected} className="flex min-h-14 items-center gap-2 px-5 text-left text-title font-semibold">
              Rejected <Count n={rejected.length} /><span className="ml-auto text-meta font-medium text-text-muted">{showRejected ? "Hide" : "Show"}</span>
            </button>
            {showRejected && (
              <ul className="border-t border-border-subtle">{rejected.map((f) => (
                <li key={f.id} className="flex items-center gap-3 border-b border-border-subtle px-5 py-2 text-body last:border-0">
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
