import { useState } from "react";
import { Camera, Eye, EyeOff } from "lucide-react";
import { useHerald } from "@/lib/store";
import { captureAction } from "./actions";

export function CaptureControl() {
  const capture = useHerald((s) => s.snapshot?.capture);
  const disabled = useHerald((s) => s.source === "fixture" || s.stale || s.conn !== "open");
  const reduced = useHerald((s) => s.ui.reducedMotion);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState("");
  async function run(path: string, body: Record<string, unknown>) {
    if (busy || disabled) return;
    setBusy(true); setError("");
    try { await captureAction(path, body); } catch (e) { setError(e instanceof Error ? e.message : "Capture request failed"); }
    finally { setBusy(false); }
  }
  const watching = capture?.sees === "watching", reading = capture?.sees === "reading";
  return <section className="flex shrink-0 flex-wrap items-center gap-3 border-b border-border-subtle bg-surface-1 px-5 py-3" aria-label="Agentic camera capture">
    <span className={`flex min-w-44 items-center gap-2 text-body ${watching || reading ? "text-herald-accent" : "text-text-muted"}`} role="status">
      {watching || reading ? <Eye size={21} className={reading && !reduced ? "motion-safe:animate-pulse" : ""} /> : <EyeOff size={21} />}
      Herald sees: {capture?.sees ?? "off"}
    </span>
    <button type="button" className="min-h-12 rounded-xl border border-border-control px-4 text-button" aria-pressed={capture?.auto ?? false} disabled={disabled || busy || !capture}
      onClick={() => void run("/api/capture/auto", { on: !capture?.auto })}>{capture?.auto ? "Turn auto off" : "Turn auto on"}</button>
    <label className="flex items-center gap-2 text-meta">Capture mode<select className="min-h-12 rounded-xl border border-border-control bg-surface-2 px-3" value={mode} disabled={busy || disabled} onChange={(e) => setMode(e.target.value)}>
      <option value="">Auto choice</option><option value="monitor">Monitor</option><option value="pill_bottle">Label</option><option value="form">Form</option><option value="scene">Scene</option>
    </select></label>
    <button type="button" className="flex min-h-12 items-center gap-2 rounded-xl bg-herald-accent px-4 text-button font-semibold text-on-accent" disabled={disabled || busy || !capture}
      onClick={() => void run("/api/capture/now", mode ? { mode } : {})}><Camera size={19} />{busy ? "Requesting…" : "Show Herald"}</button>
    <a className="ml-auto inline-flex min-h-12 items-center rounded-lg px-2 text-meta font-semibold text-herald-accent" href="/capture.html" target="_blank" rel="noreferrer">Open camera & set region ↗</a>
    <p className="w-full text-meta text-text-muted">{capture?.auto && capture.sees === "off" ? "Waiting for a camera source. " : ""}{capture?.roi ? "Monitor region set." : "Monitor watch off: set a region first."} Selected stills only · all readings need confirmation{capture?.pending ? ` · ${capture.pending} capture(s) waiting` : ""}</p>
    {(error || capture?.error) && <p role="alert" className="w-full text-meta text-medium-fg">{error || capture?.error}</p>}
  </section>;
}
