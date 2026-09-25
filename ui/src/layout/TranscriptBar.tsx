import { ManualEntry } from "@/components/ManualEntry";
import { CaptureBar } from "@/features/capture/CaptureBar";
import { summarize } from "@/features/trace/trace";
import { hhmm } from "@/lib/format";
import { useHerald } from "@/lib/store";

// One capture implementation across the detailed and ambulance workspaces.
export function TranscriptBar() {
  const snapshot = useHerald((s) => s.snapshot);
  const setUi = useHerald((s) => s.setUi);
  const t = snapshot?.transcripts.at(-1);
  return <footer id="capture-dock" className="shrink-0 bg-surface-1" aria-label="Patient capture">
    <div className="flex items-center gap-3 px-5 py-2">
      {t ? <button type="button" onClick={() => setUi({ page: "transcript" })} className="min-h-12 min-w-0 flex-1 text-left text-body">
        <span className="font-semibold">{t.speaker ?? t.captured_by} · {hhmm(t.ts)}</span>
        <span className="block truncate">{t.text}</span><span className="text-meta text-text-muted">{summarize(t)}</span>
      </button> : <p className="flex-1 text-body text-text-muted">Nothing heard yet. Hold to talk, type a note, or enter a reading.</p>}
      <ManualEntry key={snapshot?.incident.id} />
    </div>
    <CaptureBar />
  </footer>;
}
