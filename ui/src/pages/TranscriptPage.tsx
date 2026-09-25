// Transcript: everything Herald heard or was shown, newest first, with what rules and the local model extracted and
// what changed on the screen.
import { AudioLines } from "lucide-react";
import { useLayoutEffect, useRef, useState } from "react";
import type { TranscriptEntry } from "@/lib/types";
import { useHerald } from "@/lib/store";
import { Card, CardHeader, Count, EmptyState, PageHeader } from "@/components/kit";
import { TraceEntry } from "@/features/trace/trace";

export function TranscriptPage({ onReview }: { onReview?: () => void } = {}) {
  const patient = useHerald((s) => s.snapshot?.active_patient ?? s.snapshot?.incident.id);
  return <TranscriptList key={patient} onReview={onReview} />;
}

const EMPTY: TranscriptEntry[] = [];

function TranscriptList({ onReview }: { onReview?: () => void }) {
  const ts = useHerald((s) => s.snapshot?.transcripts) ?? EMPTY;
  const concise = useHerald((s) => s.ui.mode === "medic");
  const [visible, setVisible] = useState(ts);
  const top = useRef<HTMLDivElement>(null);
  // Update processing in place. Incoming captures cannot prepend rows or evict the evidence being read.
  useLayoutEffect(() => {
    setVisible((previous) => previous.length
      ? previous.map((entry) => ts.find((current) => current.id === entry.id) ?? entry)
      : ts);
  }, [ts]);
  const ids = new Set(visible.map((entry) => entry.id));
  const added = ts.filter((entry) => !ids.has(entry.id)).length;
  return (
    <div ref={top} tabIndex={-1} className="flex flex-col gap-5 px-6 pt-5 pb-6">
      <PageHeader title="Transcript" description="What Herald heard, and what it did with it. Newest first; new captures wait until you show them." />
      <Card>
        <CardHeader icon={AudioLines} cat="speech" title="Captures" actions={visible.length ? <Count n={visible.length} /> : undefined} className="pb-1" />
        <div className="min-h-12 px-5" aria-live="polite">
          {added > 0 && <button className="min-h-12 rounded-lg bg-accent-tint px-3 text-body font-semibold text-herald-accent" onClick={() => {
            setVisible(ts); top.current?.focus({ preventScroll: true }); top.current?.scrollIntoView({ block: "start" });
          }}>{added} new capture{added === 1 ? "" : "s"} · show latest</button>}
        </div>
        {visible.length === 0 ? <EmptyState icon={AudioLines} cat="speech" title="Nothing heard yet">Use capture below, or <a href="/classic/capture.html">take a photo</a>.</EmptyState>
          : [...visible].reverse().map((t) => <TraceEntry key={t.id} t={t} wide concise={concise} onReview={onReview} />)}
      </Card>
    </div>
  );
}
