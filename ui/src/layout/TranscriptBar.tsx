// Persistent capture dock: the primary medic action stays available from every page.
// Audio, typed speech and camera capture all use the local endpoints behind the classic safety-net screen.
import { ArrowUp, Camera, Keyboard, LoaderCircle, Mic, Square, UserRound, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { sourceIcon, summarize } from "@/features/trace/trace";
import { hhmm } from "@/lib/format";
import { useHerald } from "@/lib/store";
import { cn } from "@/lib/utils";
import { Button, IconTile } from "@/components/kit";
import { ManualEntry } from "@/components/ManualEntry";

type CaptureState = "idle" | "recording" | "transcribing" | "saving-photo";
type Speaker = "medic" | "other";

function concat(chunks: Float32Array[]) {
  const n = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const out = new Float32Array(n);
  let at = 0;
  for (const chunk of chunks) { out.set(chunk, at); at += chunk.length; }
  return out;
}

function downsample(input: Float32Array, from: number, to: number) {
  if (from === to) return input;
  const ratio = from / to;
  const out = new Float32Array(Math.floor(input.length / ratio));
  for (let i = 0; i < out.length; i += 1) {
    const start = Math.floor(i * ratio);
    const end = Math.min(Math.floor((i + 1) * ratio), input.length);
    let total = 0;
    for (let j = start; j < end; j += 1) total += input[j];
    out[i] = total / Math.max(1, end - start);
  }
  return out;
}

function encodeWav(samples: Float32Array, sampleRate: number) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const word = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i += 1) view.setUint8(offset + i, value.charCodeAt(i));
  };
  word(0, "RIFF"); view.setUint32(4, 36 + samples.length * 2, true); word(8, "WAVE"); word(12, "fmt ");
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true); word(36, "data");
  view.setUint32(40, samples.length * 2, true);
  samples.forEach((sample, i) => {
    const x = Math.max(-1, Math.min(1, sample));
    view.setInt16(44 + i * 2, x < 0 ? x * 0x8000 : x * 0x7fff, true);
  });
  return buffer;
}

interface ActiveRecording {
  stream: MediaStream;
  context: AudioContext;
  processor: ScriptProcessorNode;
  chunks: Float32Array[];
  speaker: Speaker;
}

export function TranscriptBar() {
  const t = useHerald((s) => s.snapshot?.transcripts.at(-1));
  const explain = useHerald((s) => s.ui.mode === "explain");
  const stale = useHerald((s) => s.stale);
  const connected = useHerald((s) => s.conn === "open" && s.snapshot !== null);
  const health = useHerald((s) => s.health);
  const source = useHerald((s) => s.source);
  const keyboardPtt = useHerald((s) => s.ui.keyboardPtt);
  const setUi = useHerald((s) => s.setUi);
  const holdAlerts = useHerald((s) => s.holdAlerts);
  const showToast = useHerald((s) => s.showToast);
  const [state, setState] = useState<CaptureState>("idle");
  const [expanded, setExpanded] = useState(false);
  const [typed, setTyped] = useState("");
  const [typedBy, setTypedBy] = useState<Speaker>("medic");
  const recording = useRef<ActiveRecording | null>(null);
  const photo = useRef<HTMLInputElement>(null);
  const requested = useRef(false);
  const starting = useRef(false);
  const mounted = useRef(true);
  const [photoMode, setPhotoMode] = useState("monitor");
  const [error, setError] = useState("");
  const unavailable = stale || !connected || source === "fixture";

  const fail = (message: string) => { setState("idle"); holdAlerts(false); setError(message); };

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false; requested.current = false;
      const active = recording.current;
      if (active) {
        active.processor.disconnect();
        active.stream.getTracks().forEach((track) => track.stop());
        void active.context.close(); recording.current = null;
      }
      holdAlerts(false);
    };
  }, [holdAlerts]);

  const startRecording = async (speaker: Speaker) => {
    if (state !== "idle" || unavailable || starting.current || explain) {
      if (source === "fixture") showToast("Replay: capture is off");
      return;
    }
    requested.current = true; starting.current = true; setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
      if (!requested.current || !mounted.current) { stream.getTracks().forEach((track) => track.stop()); return; }
      const context = new AudioContext();
      const sourceNode = context.createMediaStreamSource(stream);
      const processor = context.createScriptProcessor(4096, 1, 1);
      const chunks: Float32Array[] = [];
      processor.onaudioprocess = (event) => chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
      sourceNode.connect(processor); processor.connect(context.destination);
      recording.current = { stream, context, processor, chunks, speaker };
      holdAlerts(true); setState("recording");
    } catch {
      fail("Microphone unavailable. Open Herald on localhost or HTTPS and allow microphone access.");
    } finally { starting.current = false; }
  };

  const stopRecording = async () => {
    requested.current = false;
    const active = recording.current;
    if (!active) return;
    recording.current = null;
    active.processor.disconnect(); active.stream.getTracks().forEach((track) => track.stop());
    const sampleRate = active.context.sampleRate;
    await active.context.close();
    if (!active.chunks.length) { setState("idle"); holdAlerts(false); return; }
    setState("transcribing");
    const form = new FormData();
    form.append("file", new Blob([encodeWav(downsample(concat(active.chunks), sampleRate, 16000), 16000)], { type: "audio/wav" }), "clip.wav");
    form.append("captured_by", active.speaker);
    if (active.speaker === "other") form.append("speaker", "patient or bystander");
    try {
      const response = await fetch("/api/audio", { method: "POST", body: form, signal: AbortSignal.timeout(30000) });
      if (!response.ok) throw new Error();
      const result = await response.json();
      setState("idle"); holdAlerts(false);
      if (!result.transcript) setError("No speech recognized. Try again or use manual entry.");
    } catch { fail("Audio processing could not be confirmed. Check the latest capture before trying again."); }
  };

  useEffect(() => {
    if (explain || unavailable) { requested.current = false; if (recording.current) void stopRecording(); }
  }, [explain, unavailable]);

  useEffect(() => {
    if (!keyboardPtt || explain) return;
    const editable = (target: EventTarget | null) => target instanceof HTMLElement && (target.isContentEditable || !!target.closest("button, a, input, textarea, select, [role=dialog]"));
    const down = (event: KeyboardEvent) => {
      if (event.code !== "Space" || event.repeat || editable(event.target) || document.querySelector("[role=dialog]")) return;
      event.preventDefault(); void startRecording("medic");
    };
    const up = (event: KeyboardEvent) => {
      if (event.code !== "Space" || !requested.current) return;
      event.preventDefault(); void stopRecording();
    };
    const blur = () => { void stopRecording(); };
    window.addEventListener("blur", blur);
    document.addEventListener("keydown", down); document.addEventListener("keyup", up);
    return () => { window.removeEventListener("blur", blur); document.removeEventListener("keydown", down); document.removeEventListener("keyup", up); };
  });

  const sendTyped = async (event: React.FormEvent) => {
    event.preventDefault();
    const text = typed.trim();
    if (!text || unavailable || state !== "idle") return;
    setError("");
    setState("transcribing");
    holdAlerts(true);
    try {
      const response = await fetch("/api/transcript", {
        method: "POST", headers: { "Content-Type": "application/json" }, signal: AbortSignal.timeout(30000),
        body: JSON.stringify({ text, captured_by: typedBy, speaker: typedBy === "other" ? "patient or bystander" : null }),
      });
      if (!response.ok) throw new Error();
      setTyped(""); setExpanded(false); setState("idle"); holdAlerts(false);
    } catch { fail("Typed capture could not be confirmed. Your text is retained here. Check the latest capture before trying again."); }
  };

  const sendPhoto = async (file: File | undefined) => {
    if (!file || unavailable || state !== "idle") return;
    setError("");
    setState("saving-photo");
    holdAlerts(true);
    const form = new FormData(); form.append("file", file); form.append("mode", photoMode);
    try {
      const response = await fetch("/api/photo", { method: "POST", body: form, signal: AbortSignal.timeout(60000) });
      if (!response.ok) throw new Error();
      setState("idle"); holdAlerts(false);
    } catch { fail("Photo processing could not be confirmed. Review the latest capture or enter the value manually."); }
    if (photo.current) photo.current.value = "";
  };

  if (explain) return null;
  const busy = state !== "idle" && state !== "recording";
  return (
    <footer id="capture-dock" className="mx-5 mb-4 shrink-0 rounded-[18px] bg-surface-1 px-3 py-2.5 shadow-[var(--shadow-3)] max-lg:mx-3" aria-label="Patient capture">
      {error && <p role="alert" className="mb-2 rounded-xl bg-low-tint px-3 py-2 text-body text-low-fg">{error}</p>}
      {source !== "fixture" && connected && !health?.llm_model && <p className="mb-2 text-meta text-text-muted">Language model unavailable. Verify speech extraction carefully or use manual entry.</p>}
      {source !== "fixture" && connected && health && !health.stt_loaded && <p className="mb-2 text-meta text-text-muted">Speech recognition is warming up. Manual entry is available now.</p>}
      {expanded && (
        <form onSubmit={sendTyped} className="mb-2 flex flex-wrap items-center gap-2 border-b border-border-subtle pb-2">
          <select value={typedBy} onChange={(event) => setTypedBy(event.target.value as Speaker)} aria-label="Who said this"
            className="h-11 rounded-[var(--radius-control)] bg-surface-2 px-3 text-body text-text-primary">
            <option value="medic">Medic</option><option value="other">Patient / bystander</option>
          </select>
          <input autoFocus value={typed} onChange={(event) => setTyped(event.target.value)} placeholder="Type what was said or a manual correction"
            className="h-11 min-w-0 flex-1 rounded-[var(--radius-control)] border border-border-control bg-surface-2 px-3 text-body text-text-primary placeholder:text-text-muted" />
          <Button type="submit" variant="primary" size="lg" disabled={!typed.trim() || state !== "idle" || unavailable}><ArrowUp size={18} />Save</Button>
          <Button aria-label="Close typed capture" onClick={() => setExpanded(false)} size="lg"><X size={18} /></Button>
        </form>
      )}
      <div className="flex min-h-14 flex-wrap items-center gap-2.5">
        <button type="button" disabled={busy || (unavailable && state !== "recording")} aria-label={state === "recording" ? "Release to stop medic recording" : "Hold to record the medic"}
          onKeyDown={(event) => { if ([" ", "Enter"].includes(event.key) && !event.repeat) { event.preventDefault(); void startRecording("medic"); } }}
          onKeyUp={(event) => { if ([" ", "Enter"].includes(event.key)) { event.preventDefault(); void stopRecording(); } }}
          onPointerDown={(event) => { event.currentTarget.setPointerCapture(event.pointerId); void startRecording("medic"); }}
          onPointerUp={() => void stopRecording()} onPointerCancel={() => void stopRecording()} onLostPointerCapture={() => void stopRecording()}
          className={cn("hit flex h-14 shrink-0 items-center gap-2 rounded-[16px] px-5 text-button font-bold text-white transition-[filter,transform] disabled:opacity-45",
            state === "recording" ? "ring-2 ring-capture bg-accent-fill" : "bg-accent-fill hover:brightness-110")}>
          {state === "recording" ? <><span className="size-2.5 animate-pulse rounded-sm bg-white" />Release to save</> : busy ? <><LoaderCircle size={19} className="animate-spin" />Processing</> : <><Mic size={20} />Hold to speak</>}
        </button>
        {state === "recording" && <Button onClick={() => void stopRecording()}><Square size={16} />Stop recording</Button>}
        <button type="button" disabled={busy || unavailable} aria-label="Hold to record patient or bystander"
          onKeyDown={(event) => { if ([" ", "Enter"].includes(event.key) && !event.repeat) { event.preventDefault(); void startRecording("other"); } }}
          onKeyUp={(event) => { if ([" ", "Enter"].includes(event.key)) { event.preventDefault(); void stopRecording(); } }}
          onPointerDown={(event) => { event.currentTarget.setPointerCapture(event.pointerId); void startRecording("other"); }}
          onPointerUp={() => void stopRecording()} onPointerCancel={() => void stopRecording()}
          className="hit flex h-11 shrink-0 items-center gap-2 rounded-xl bg-surface-2 px-3 text-body text-text-primary hover:bg-surface-3 disabled:opacity-45"><UserRound size={19} />Other speaker</button>
        <Button disabled={state !== "idle" || unavailable} onClick={() => setExpanded(!expanded)} aria-expanded={expanded} aria-label="Type patient information"><Keyboard size={19} />Type</Button>
        <ManualEntry />
        <select aria-label="Photo type" value={photoMode} disabled={state !== "idle" || unavailable} onChange={(e) => setPhotoMode(e.target.value)} className="h-11 rounded-xl bg-surface-2 px-3 text-body">
          <option value="monitor">Monitor</option><option value="pill_bottle">Pill bottle</option><option value="form">POLST / DNR form</option><option value="scene">Scene</option>
        </select>
        <Button disabled={state !== "idle" || unavailable} onClick={() => photo.current?.click()} aria-label="Capture a monitor or document photo"><Camera size={19} />Photo</Button>
        <input ref={photo} type="file" accept="image/*" capture="environment" className="hidden" onChange={(event) => void sendPhoto(event.target.files?.[0])} />
        <div className="flex w-full min-w-0 items-center gap-3 border-t border-border-subtle pt-2">
        <IconTile icon={sourceIcon(t)} cat="speech" size={32} />
        {t ? (
          <button type="button" onClick={() => setUi({ page: "transcript" })} className="flex min-h-11 min-w-0 flex-1 items-center gap-2 text-left text-body" aria-live="polite">
            <span className="shrink-0 font-semibold text-cat-speech-fg">{t.speaker ?? t.captured_by}</span>
            <span className="truncate text-text-primary">“{t.text}”</span>
            <span className="hidden shrink-0 text-meta text-text-muted xl:inline">{summarize(t)}</span>
            <span className="num ml-auto shrink-0 text-meta text-text-muted">{hhmm(t.ts)}</span>
          </button>
        ) : <p className="min-w-0 flex-1 text-body text-text-muted">{unavailable ? "Capture unavailable until the live patient record connects." : "Hold the blue button while speaking, or enter a value manually."}</p>}
        </div>
      </div>
    </footer>
  );
}
