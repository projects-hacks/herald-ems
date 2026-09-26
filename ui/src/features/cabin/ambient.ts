import { authHeaders } from "@/lib/authToken";
import { UNIDENTIFIED_SPEAKER } from "@/lib/format";

import { Endpointer } from "./endpoint";
import { join, wav } from "./pcm";

/** `waitingTap`: the browser holds audio until the first touch on the page (autoplay policy). `warning`: capture goes
 *  on but something needs the medic to know (clips held while the server is unreachable, speech that was lost);
 *  `lost`: utterances that could not be processed in this session. Only `error` means the microphone stopped. */
export interface AmbientStatus { listening: boolean; starting: boolean; queued: number; level: number; message: string; error: boolean;
  waitingTap?: boolean; warning?: string | null; lost?: number }
export const initialAmbient: AmbientStatus = { listening: false, starting: false, queued: 0, level: 0, message: "Microphone off", error: false };

// Continuous capture keeps going through what a moving vehicle does to it: a slow or unreachable server (clips wait
// and are retried), a burst of speech (the oldest waiting clip gives way, and says so), the browser suspending audio
// (it resumes on the next touch), a microphone that drops out (it is reopened). It stops only when the medic pauses,
// the call changes, or the microphone cannot be opened at all.
const QUEUE_MAX = 8;                              // utterances waiting to upload (about a minute of talk)
const RETRY_MS = [1000, 2000, 4000, 8000];        // per utterance, then it is counted as lost
const UPLOAD_TIMEOUT_MS = 30000;

/** One session, bound to one incident. Nothing persists in browser storage. */
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
  private reopening = false;
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
      stream.getAudioTracks().forEach((t) => { t.onended = () => void this.reopen(); });   // a device change or unplug
      context.onstatechange = () => { if (context.state === "suspended" && this.state.listening && token === this.generation) this.holdForTouch(context); };
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
      this.update({ starting: false, listening: true, waitingTap: false, message: "Listening · speech is processed on the vehicle" });
    } catch (e) { if (token === this.generation && !this.disposed) this.fail(e instanceof Error ? e.message : "Microphone unavailable"); }
  }

  /** The browser suspended audio mid-session (focus, a headset change): resume now if allowed, else on the next touch. */
  private holdForTouch(context: AudioContext) {
    void context.resume();
    if (context.state === "running") return;
    this.update({ waitingTap: true, message: "Tap anywhere to resume listening" });
    const go = () => { void context.resume().then(() => { if (context.state === "running") this.update({ waitingTap: false, message: "Listening · speech is processed on the vehicle" }); }); };
    document.addEventListener("pointerdown", go, { once: true }); document.addEventListener("keydown", go, { once: true });
  }

  /** The microphone track ended (unplugged, switched): open the current default device again, once. */
  private async reopen() {
    if (this.reopening || this.disposed || !this.state.listening) return;
    this.reopening = true;
    this.pause(true);
    this.update({ warning: "Microphone changed, reconnecting" });
    await new Promise((done) => window.setTimeout(done, 800));
    this.reopening = false;
    if (this.disposed) return;
    await this.start();
    if (this.state.listening) this.update({ warning: null });
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
    if (this.queue.length >= QUEUE_MAX) {       // a long outage: the oldest words give way, and the medic is told
      this.queue.shift();
      this.lose("Speech is arriving faster than it can be processed");
    }
    this.queue.push(wav(audio, this.rate));
    this.update({ queued: this.queue.length + Number(this.uploading) });
    void this.drain();
  }

  private lose(why: string) {
    const lost = (this.state.lost ?? 0) + 1;
    this.update({ lost, warning: `${why}: ${lost} ${lost === 1 ? "clip" : "clips"} not processed; repeat key facts or type them` });
  }

  /** One utterance to the vehicle server. "retry": the server or the link failed; "drop": this clip can never land. */
  private async upload(blob: Blob): Promise<"ok" | "retry" | "drop"> {
    const form = new FormData(); form.append("file", blob, "ambient.wav");
    form.append("incident_id", this.incident); form.append("captured_by", "other");
    form.append("ambient", "true");
    form.append("speaker", UNIDENTIFIED_SPEAKER);
    this.abort = new AbortController();
    const timeout = window.setTimeout(() => this.abort?.abort(), UPLOAD_TIMEOUT_MS);
    try {
      const response = await fetch("/api/audio", { method: "POST", headers: authHeaders(), body: form, signal: this.abort.signal });
      if (response.ok) { await response.json().catch(() => null); return "ok"; }
      return response.status >= 500 ? "retry" : "drop";   // 409: the call changed; 4xx: the clip itself is unusable
    } catch {
      return this.disposed ? "drop" : "retry";          // unreachable, timed out
    } finally { window.clearTimeout(timeout); }
  }

  private async drain() {
    if (this.uploading || this.disposed) return;
    this.uploading = true;
    while (this.queue.length && !this.disposed) {
      const blob = this.queue[0];
      let outcome = await this.upload(blob);
      for (let i = 0; outcome === "retry" && i < RETRY_MS.length && !this.disposed; i++) {
        this.update({ warning: `Can't reach the vehicle server, holding ${this.queue.length} ${this.queue.length === 1 ? "clip" : "clips"}, retrying` });
        await new Promise((done) => window.setTimeout(done, RETRY_MS[i]));
        outcome = await this.upload(blob);
      }
      if (this.disposed) break;
      if (this.queue[0] === blob) this.queue.shift();
      if (outcome === "ok") { if (this.state.warning?.startsWith("Can't reach")) this.update({ warning: null }); }
      else if (outcome === "retry") this.lose("The vehicle server did not answer");
      this.update({ queued: this.queue.length });
    }
    this.uploading = false; this.update({ queued: this.queue.length });
  }

  /** The microphone could not be opened: the one case that stops capture. Waiting clips still upload. */
  private fail(message: string) {
    this.pause(false); this.update({ error: true, message });
  }
  dispose() { this.disposed = true; this.pause(false); this.queue = []; this.abort?.abort(); }
}
