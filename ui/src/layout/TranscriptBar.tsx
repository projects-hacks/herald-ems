// The bottom bar (UX_PLAN §3.1.10): the newest capture and what it did, one line. Voice capture lives on the classic
// screen until U4. Hidden in explain mode, where the full trace is on the page.
import { ArrowUpRight } from "lucide-react";
import { hhmm } from "@/lib/format";
import { useHerald } from "@/lib/store";
import { sourceIcon, summarize } from "@/features/trace/trace";

export function TranscriptBar() {
  const t = useHerald((s) => s.snapshot?.transcripts.at(-1));
  const explain = useHerald((s) => s.ui.mode === "explain");
  const setUi = useHerald((s) => s.setUi);
  if (explain) return null;
  const Icon = sourceIcon(t);
  return (
    <footer className="flex min-h-16 shrink-0 items-center gap-3 border-t border-border-subtle bg-surface-1/95 px-7 backdrop-blur-xl">
      <span className="grid size-8 shrink-0 place-items-center rounded-full bg-accent-tint text-herald-accent" aria-hidden><Icon size={15} /></span>
      {t ? (
        <button type="button" onClick={() => setUi({ page: "transcript" })} className="flex min-h-11 min-w-0 flex-1 items-center gap-2.5 text-left text-body" aria-live="polite"
          aria-label={`Last heard at ${hhmm(t.ts)}, ${t.speaker ?? t.captured_by}: ${t.text}. ${summarize(t)}. Open the transcript.`}>
          <span className="label-caps shrink-0 text-text-muted">Last heard</span>
          <span className="num shrink-0 text-text-muted">{hhmm(t.ts)}</span>
          <span className="shrink-0 font-semibold">{t.speaker ?? t.captured_by}</span>
          <span className="truncate text-text-secondary">“{t.text}”</span>
          <span className="hidden shrink-0 text-meta text-text-muted xl:inline">→ {summarize(t)}</span>
        </button>
      ) : (
        <p className="min-w-0 flex-1 truncate text-body text-text-muted">Nothing heard yet. Speak, or take a photo at {location.host}/capture.html</p>
      )}
      <a href="/classic/" className="hit inline-flex h-10 shrink-0 items-center gap-1.5 rounded-full bg-accent-tint px-4 text-meta font-semibold text-herald-accent hover:brightness-95">
        Voice capture<ArrowUpRight size={14} aria-hidden />
      </a>
    </footer>
  );
}
