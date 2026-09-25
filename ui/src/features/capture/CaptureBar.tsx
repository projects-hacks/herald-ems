import { useEffect, useState } from "react";
import { Button } from "@/components/kit";
import { useHerald } from "@/lib/store";
import { useContract } from "@/lib/contract";
import { livePatient, submitCapture } from "./client";
import { useRecorder } from "./useRecorder";

export function CaptureBar({ allowVoice = true }: { allowVoice?: boolean }) {
  const disabled = useHerald((s) => s.source === "fixture" || s.stale || s.conn !== "open");
  const keyboard = useHerald((s) => s.ui.keyboardPtt);
  const activePatient = useHerald((s) => s.snapshot?.incident.id);
  const recorder = useRecorder(), contract = useContract();
  const [text, setText] = useState(""), [speaker, setSpeaker] = useState(""), [by, setBy] = useState("medic");
  const [key, setKey] = useState("vitals.hr"), [value, setValue] = useState(""), [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const keys = Object.entries(contract?.keys ?? {}).filter(([k, meta]) => k.startsWith("vitals.") && ["int", "float", "number", "bool"].includes(meta.type));
  const boolean = contract?.keys[key]?.type === "bool";
  useEffect(() => { setText(""); setValue(""); setSpeaker(""); setBy("medic"); setError(""); }, [activePatient]);
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      const target = e.target instanceof HTMLElement ? e.target : null;
      if (!allowVoice || !keyboard || disabled || e.repeat || e.ctrlKey || e.altKey || e.metaKey || target?.closest("input,textarea,select,button,a,[contenteditable=true],[role=dialog]") || document.querySelector('[role="dialog"]')) return;
      if (e.code === "Space" || e.code === "KeyF") { e.preventDefault(); void recorder.start(e.code === "Space" ? "medic" : "other", speaker); }
    };
    const up = (e: KeyboardEvent) => { if (e.code === "Space" || e.code === "KeyF") void recorder.stop(); };
    window.addEventListener("keydown", down); window.addEventListener("keyup", up);
    return () => { window.removeEventListener("keydown", down); window.removeEventListener("keyup", up); };
  }, [disabled, allowVoice, keyboard, recorder.start, recorder.stop, speaker]);
  async function submit(kind: "text" | "monitor") {
    if (busy || disabled) return;
    setBusy(true); setError("");
    try {
      const patient = livePatient();
      if (kind === "text") {
        await submitCapture("/api/transcript", { text: text.trim(), captured_by: by, speaker: by === "other" ? speaker || null : null }, patient);
        if (useHerald.getState().snapshot?.incident.id === patient) setText("");
      } else {
        if (boolean ? !["true", "false"].includes(value) : !value.trim() || !Number.isFinite(Number(value))) throw new Error("Enter a valid monitor value.");
        await submitCapture("/api/facts", [{ key, value: boolean ? value === "true" : Number(value), captured_by: "device", role: "device", speaker: "manual monitor entry", confidence: 1 }], patient);
        if (useHerald.getState().snapshot?.incident.id === patient) setValue("");
      }
    } catch (e) { setError(e instanceof Error ? e.message : "Capture failed. Review the transcript before retrying."); }
    finally { setBusy(false); }
  }
  return <section aria-label="Capture speech and readings" className="shrink-0 border-t border-border-subtle bg-surface-1 px-5 py-3">
    <div className="flex flex-wrap items-center gap-3">
      {(["medic", "other"] as const).map((source) => <Button key={source} variant={source === "medic" ? "primary" : "secondary"} disabled={disabled || busy || !allowVoice}
        onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); void recorder.start(source, speaker); }} onPointerUp={() => void recorder.stop()} onPointerCancel={() => void recorder.stop(false)}
        onKeyDown={(e) => { if (!e.repeat && [" ", "Enter"].includes(e.key)) { e.preventDefault(); void recorder.start(source, speaker); } }}
        onKeyUp={(e) => { if ([" ", "Enter"].includes(e.key)) { e.preventDefault(); void recorder.stop(); } }}>
        Hold to talk · {source}{keyboard ? source === "medic" ? " (Space)" : " (F)" : ""}</Button>)}
      <label className="text-meta">Other speaker<input className="ml-2 min-h-12 w-36 rounded-lg border border-border-control bg-surface-2 px-3" value={speaker} onChange={(e) => setSpeaker(e.target.value)} placeholder="Name or role" /></label>
      <a href="/classic/capture.html" className="inline-flex min-h-12 items-center px-3 text-herald-accent">Take a photo ↗</a>
      <span role="status" className="text-meta">{recorder.status || "Mic off · clips limited to 30 seconds"}</span>
    </div>
    <details className="mt-2"><summary className="min-h-12 cursor-pointer py-3 text-body">Type a note or enter a monitor reading</summary>
      <fieldset disabled={disabled || busy}>
      <form className="flex flex-wrap gap-2 py-2" onSubmit={(e) => { e.preventDefault(); void submit("text"); }}>
        <label className="flex flex-1 flex-col text-meta">Spoken or typed note<textarea required value={text} onChange={(e) => setText(e.target.value)} className="min-h-16 rounded-lg border border-border-control bg-surface-2 p-3" /></label>
        <label className="text-meta">Source<select value={by} onChange={(e) => setBy(e.target.value)} className="block min-h-12 bg-surface-2"><option value="medic">Medic</option><option value="other">Other speaker</option></select></label>
        <Button type="submit" disabled={disabled || busy || !text.trim()}>Submit note</Button>
      </form>
      <form className="flex flex-wrap items-end gap-2 py-2" onSubmit={(e) => { e.preventDefault(); void submit("monitor"); }}>
        <label className="text-meta">Monitor reading<select value={key} onChange={(e) => { setKey(e.target.value); setValue(""); }} className="block min-h-12 bg-surface-2">{keys.map(([k, m]) => <option value={k} key={k}>{m.label}{m.unit ? ` (${m.unit})` : ""}</option>)}</select></label>
        <label className="text-meta">Value{boolean ? <select required value={value} onChange={(e) => setValue(e.target.value)} className="block min-h-12 bg-surface-2"><option value="">Choose</option><option value="false">No</option><option value="true">Yes</option></select> : <input type="number" step={contract?.keys[key]?.type === "int" ? 1 : "any"} required value={value} onChange={(e) => setValue(e.target.value)} className="block min-h-12 w-28 rounded-lg border border-border-control bg-surface-2 px-3" />}</label>
        <Button type="submit" disabled={disabled || busy || !keys.length}>Record reading</Button><span className="text-meta text-text-muted">Entered as a confirmed device reading. Check before submitting.</span>
      </form>
      </fieldset>
    </details>
    {(error || recorder.error) && <p role="alert" className="mt-2 text-body text-medium-fg">{error || recorder.error}</p>}
  </section>;
}
