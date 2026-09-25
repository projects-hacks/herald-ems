import { authHeaders } from "@/lib/authToken";
import { UNIDENTIFIED_SPEAKER } from "@/lib/format";

import { Endpointer } from "./endpoint";
import { join, wav } from "./pcm";

/** `waitingTap`: the browser holds audio until the first touch on the page (autoplay policy). */
export interface AmbientStatus { listening: boolean; starting: boolean; queued: number; level: number; message: string; error: boolean; waitingTap?: boolean }
export const initialAmbient: AmbientStatus = { listening: false, starting: false, queued: 0, level: 0, message: "Microphone off", error: false };

/** One explicitly started session, bound to one incident. Nothing persists in browser storage. */
export class AmbientCapture {
  private state = { ...initialAmbient };
  private stream?: MediaStream;
  private context?: AudioContext;
  private node?: AudioWorkletNode;
  private endpoint?: Endpointer;
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
    if (this.disposed || this.state.starting || this.state.listening) return;
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
      const endpoint = new Endpointer(this.rate); this.endpoint = endpoint;   // only speech is sent, cut at pauses
      node.port.onmessage = (e: MessageEvent<Float32Array>) => {
        if (!this.state.listening) return;
        const chunk = e.data;
        const rms = Math.sqrt(chunk.reduce((sum, n) => sum + n * n, 0) / chunk.length);
        this.update({ level: Math.min(1, rms * 8) });
        const said = endpoint.push(chunk);
        if (said) this.send(said);
      };
      const mute = context.createGain(); mute.gain.value = 0;
      context.createMediaStreamSource(stream).connect(node); node.connect(mute); mute.connect(context.destination);
      stream.getAudioTracks().forEach((t) => { t.onended = () => this.fail("Microphone disconnected. Capture stopped; check the record for missing speech."); });
      context.onstatechange = () => { if (context.state === "suspended" && this.state.listening) this.fail("Audio suspended by the browser. Tap Resume listening when ready."); };
      void context.resume();
      if (context.state === "suspended") {        // started without a tap: the browser holds audio until the first touch
        this.update({ message: "Tap anywhere to start listening", waitingTap: true });
        await new Promise<void>((done) => {
          const go = () => { void context.resume().then(() => done()); };
          document.addEventListener("pointerdown", go, { once: true }); document.addEventListener("keydown", go, { once: true });
          context.addEventListener?.("statechange", () => { if (context.state === "running") done(); });
        });
      }
      if (token !== this.generation || this.disposed) return;
      this.update({ starting: false, listening: true, waitingTap: false, message: "Listening · short clips processed locally" });
    } catch (e) { if (token === this.generation && !this.disposed) this.fail(e instanceof Error ? e.message : "Microphone unavailable"); }
  }

  pause(flush = true) {
    ++this.generation;
    this.update({ listening: false, starting: false, waitingTap: false, level: 0, message: "Microphone off · paused" });
    if (this.node) { this.node.port.onmessage = null; this.node.disconnect(); this.node = undefined; }
    this.stream?.getTracks().forEach((t) => { t.onended = null; t.stop(); }); this.stream = undefined;
    if (this.context) { this.context.onstatechange = null; void this.context.close(); this.context = undefined; }
    const rest = this.endpoint?.end(); this.endpoint = undefined;
    if (flush && rest) this.send(rest);
  }

  private send(blocks: Float32Array[]) {
    const audio = join(blocks);
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
      form.append("speaker", UNIDENTIFIED_SPEAKER);
      this.abort = new AbortController();
      const timeout = window.setTimeout(() => this.abort?.abort(), 60000);
      try {
        const response = await fetch("/api/audio", { method: "POST", headers: authHeaders(), body: form, signal: this.abort.signal });
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
