// Transcript: everything Herald heard or was shown, newest first, with what rules and the local model extracted and
// what changed on the screen.
import { AudioLines } from "lucide-react";
import { useHerald } from "@/lib/store";
import { Card, CardHeader, Count, EmptyState, PageHeader } from "@/components/kit";
import { TraceEntry } from "@/features/trace/trace";

export function TranscriptPage() {
  const ts = useHerald((s) => s.snapshot?.transcripts) ?? [];
  return (
    <div className="flex flex-col gap-5 px-6 pt-5 pb-6">
      <PageHeader title="Transcript" description="What Herald heard, and what it did with it. The last 20 captures, newest first." />
      <Card>
        <CardHeader icon={AudioLines} cat="speech" title="Captures" actions={ts.length ? <Count n={ts.length} /> : undefined} className="pb-1" />
        {ts.length === 0 ? <EmptyState icon={AudioLines} cat="speech" title="Nothing heard yet">Use capture below, or <a href="/classic/capture.html">take a photo</a>.</EmptyState>
          : [...ts].reverse().map((t) => <TraceEntry key={t.id} t={t} wide />)}
      </Card>
    </div>
  );
}
