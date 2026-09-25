import { useCallback, useEffect, useRef, useState } from "react";
import { useHerald } from "@/lib/store";
import { encodeWav } from "./pcm";
import { livePatient, submitCapture } from "./client";

type Recording = { stream: MediaStream; context: AudioContext; node: ScriptProcessorNode; source: MediaStreamAudioSourceNode;
  chunks: Float32Array[]; patient: string; by: "medic" | "other"; speaker: string; limit: number };
export function useRecorder() {
  const session = useRef<Recording | null>(null), generation = useRef(0), requesting = useRef(false), sending = useRef(false);
  const [status, setStatus] = useState(""), [error, setError] = useState("");
  const patient = useHerald((s) => s.snapshot?.incident.id);
  const available = useHerald((s) => s.source === "live" && s.conn === "open" && !s.stale);
  const stop = useCallback(async (send = true) => {
    generation.current++; requesting.current = false;
    const r = session.current; session.current = null;
    useHerald.getState().holdAlerts(false);
    if (!r) { setStatus(""); return; }
    clearTimeout(r.limit); r.node.onaudioprocess = null; r.node.disconnect(); r.source.disconnect();
    r.stream.getTracks().forEach((t) => t.stop()); void r.context.close();
    if (!send || !r.chunks.length) { setStatus(""); return; }
    sending.current = true; setStatus("Transcribing…");
    const data = new FormData(); data.append("file", encodeWav(r.chunks, r.context.sampleRate), "clip.wav");
    data.append("captured_by", r.by); if (r.by === "other" && r.speaker.trim()) data.append("speaker", r.speaker.trim());
    try { await submitCapture("/api/audio", data, r.patient); setStatus(useHerald.getState().snapshot?.incident.id === r.patient ? "Clip submitted; review the transcript." : "Previous patient's clip submitted to their record."); }
    catch (e) { setError(e instanceof Error ? e.message : "Audio submission failed. Check the transcript before retrying."); setStatus(""); }
    finally { sending.current = false; }
  }, []);
  const start = useCallback(async (by: "medic" | "other", speaker = "") => {
    if (requesting.current || session.current || sending.current) return;
    const token = ++generation.current;
    requesting.current = true; setError(""); setStatus("Waiting for microphone…");
    let stream: MediaStream | null = null, context: AudioContext | null = null;
    try {
      const owner = livePatient();
      if (!navigator.mediaDevices?.getUserMedia) throw new Error("Microphone requires HTTPS or localhost. You can use typed input below.");
      stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
      if (token !== generation.current || livePatient() !== owner) { stream.getTracks().forEach((t) => t.stop()); return; }
      context = new AudioContext(); await context.resume();
      if (token !== generation.current) { stream.getTracks().forEach((t) => t.stop()); void context.close(); return; }
      const source = context.createMediaStreamSource(stream), node = context.createScriptProcessor(4096, 1, 1);
      const chunks: Float32Array[] = [];
      node.onaudioprocess = (event) => { if (chunks.length * 4096 < context!.sampleRate * 30) chunks.push(new Float32Array(event.inputBuffer.getChannelData(0))); };
      source.connect(node); node.connect(context.destination);
      session.current = { stream, context, source, node, chunks, patient: owner, by, speaker, limit: window.setTimeout(() => void stop(), 30000) };
      stream.getTracks().forEach((t) => { t.onended = () => void stop(false); });
      useHerald.getState().holdAlerts(true); setStatus(`Recording ${by === "medic" ? "medic" : "other speaker"} · release to send`);
    } catch (e) {
      stream?.getTracks().forEach((t) => t.stop()); if (context) void context.close();
      if (token === generation.current) { setStatus(""); setError(e instanceof Error ? e.message : "Microphone unavailable"); }
    } finally { if (token === generation.current) requesting.current = false; }
  }, [stop]);
  useEffect(() => { void stop(false); }, [patient, available, stop]);
  useEffect(() => {
    const cancel = () => void stop(false);
    const hidden = () => { if (document.hidden) cancel(); };
    window.addEventListener("blur", cancel); document.addEventListener("visibilitychange", hidden);
    return () => { cancel(); window.removeEventListener("blur", cancel); document.removeEventListener("visibilitychange", hidden); };
  }, [stop]);
  return { start, stop, status, error };
}
