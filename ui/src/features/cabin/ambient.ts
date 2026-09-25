import { join, wav } from "./pcm";

export interface AmbientStatus { listening: boolean; starting: boolean; queued: number; level: number; message: string; error: boolean }
export const initialAmbient: AmbientStatus = { listening: false, starting: false, queued: 0, level: 0, message: "Microphone off", error: false };

/** One explicitly started session, bound to one incident. Nothing persists in browser storage. */
export class AmbientCapture {
  private state = { ...initialAmbient };
  private stream?: MediaStream;
  private context?: AudioContext;
  private node?: AudioWorkletNode;
  private chunks: Float32Array[] = [];
  private samples = 0;
  private rate = 48000;
  private generation = 0;
  private disposed = false;
  private queue: Blob[] = [];
  private uploading = false;
  private abort?: AbortController;
  private incident: string;
  private changed: (s: AmbientStatus) => void;
  constructor(incident: string, changed: (s: AmbientStatus) => void) { this.incident = incident; this.changed = changed; }
  private update(patch: Partial<AmbientStatus>) { this.state = { ...this.state, ...patch }; if (!this.disposed) this.changed(this.state); }

  async start() {
    if (this.disposed || this.state.starting || this.state.listening || this.uploading || this.queue.length) return;
    const token = ++this.generation;
    this.update({ starting: true, error: false, message: "Allow microphone access…" });
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error("Microphone needs HTTPS or localhost. Manual entry is still available.");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true }, video: false });
      if (token !== this.generation || this.disposed) { stream.getTracks().forEach((t) => t.stop()); return; }
      this.stream = stream;
      const context = new AudioContext(); this.context = context; this.rate = context.sampleRate;
      await context.audioWorklet.addModule("/audio/cabin-recorder.js");
      if (token !== this.generation || this.disposed) return;
      const node = new AudioWorkletNode(context, "cabin-recorder"); this.node = node;
      node.port.onmessage = (e: MessageEvent<Float32Array>) => {
        if (!this.state.listening) return;
        const chunk = e.data;
        this.chunks.push(chunk); this.samples += chunk.length;
        const rms = Math.sqrt(chunk.reduce((sum, n) => sum + n * n, 0) / chunk.length);
        this.update({ level: Math.min(1, rms * 8) });
        if (this.samples >= this.rate * 8) this.flush();
      };
      const mute = context.createGain(); mute.gain.value = 0;
      context.createMediaStreamSource(stream).connect(node); node.connect(mute); mute.connect(context.destination);
      stream.getAudioTracks().forEach((t) => { t.onended = () => this.fail("Microphone disconnected. Capture stopped; check the record for missing speech."); });
      context.onstatechange = () => { if (context.state === "suspended" && this.state.listening) this.fail("Audio suspended by the browser. Tap Resume listening when ready."); };
      await context.resume();
      if (token !== this.generation || this.disposed) return;
      this.update({ starting: false, listening: true, message: "Listening · short clips processed locally" });
    } catch (e) { if (token === this.generation && !this.disposed) this.fail(e instanceof Error ? e.message : "Microphone unavailable"); }
  }

  pause(flush = true) {
    ++this.generation;
    this.update({ listening: false, starting: false, level: 0, message: "Microphone off · paused" });
    if (this.node) { this.node.port.onmessage = null; this.node.disconnect(); this.node = undefined; }
    this.stream?.getTracks().forEach((t) => { t.onended = null; t.stop(); }); this.stream = undefined;
    if (this.context) { this.context.onstatechange = null; void this.context.close(); this.context = undefined; }
    if (flush) this.flush(); else { this.chunks = []; this.samples = 0; }
  }

  private flush() {
    if (!this.samples) return;
    const audio = join(this.chunks); this.chunks = []; this.samples = 0;
    if (this.queue.length >= 2) { this.fail("Processing cannot keep up. Capture stopped; an unsent clip was discarded. Use manual entry for missing speech."); return; }
    this.queue.push(wav(audio, this.rate));
    this.update({ queued: this.queue.length + Number(this.uploading) });
    void this.drain();
  }

  private async drain() {
    if (this.uploading || this.disposed) return;
    this.uploading = true;
    while (this.queue.length && !this.disposed) {
      const blob = this.queue.shift()!;
      const form = new FormData(); form.append("file", blob, "ambient.wav");
      form.append("incident_id", this.incident); form.append("captured_by", "other");
      form.append("ambient", "true");
      form.append("speaker", "Ambient audio · speaker unverified");
      this.abort = new AbortController();
      const timeout = window.setTimeout(() => this.abort?.abort(), 60000);
      try {
        const response = await fetch("/api/audio", { method: "POST", body: form, signal: this.abort.signal });
        if (!response.ok) throw new Error(response.status === 409 ? "Patient changed. Recording was not added to the current patient." : `Audio processing failed (${response.status}).`);
        await response.json();
        if (!this.state.error) this.update({ message: this.state.listening ? "Listening · latest clip processed" : "Microphone off · clips processed" });
      } catch (e) {
        if (!this.disposed && !this.state.error) this.fail(`${e instanceof Error ? e.message : "Audio processing failed"} Check captured notes before retrying; unsent clips were discarded.`);
        break;
      } finally { window.clearTimeout(timeout); }
      this.update({ queued: this.queue.length });
    }
    this.uploading = false; this.update({ queued: 0 });
  }

  private fail(message: string) {
    this.pause(false); this.queue = []; this.update({ error: true, message, queued: Number(this.uploading) });
  }
  dispose() { this.disposed = true; this.pause(false); this.queue = []; this.abort?.abort(); }
}
