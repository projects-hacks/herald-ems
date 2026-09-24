// Transcript: everything Herald heard or was shown, newest first, with what rules and the local model extracted and
// what changed on the screen.
import { AudioLines } from "lucide-react";
import { useHerald } from "@/lib/store";
import { Card, EmptyState, PageHeader } from "@/components/kit";
import { TraceEntry } from "@/features/trace/trace";

export function TranscriptPage() {
  const ts = useHerald((s) => s.snapshot?.transcripts) ?? [];
  return (
    <div className="flex flex-col gap-5 p-6">
      <PageHeader title="Transcript" description="What Herald heard, and what it did with it. The last 20 captures, newest first." />
      <Card>
        {ts.length === 0 ? <EmptyState icon={AudioLines} tone="neutral" title="Nothing heard yet">Speak, or take a photo at {location.host}/capture.html</EmptyState>
          : [...ts].reverse().map((t) => <TraceEntry key={t.id} t={t} wide />)}
      </Card>
    </div>
  );
}
