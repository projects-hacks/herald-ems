import { authHeaders } from "@/lib/authToken";

export interface MonitorStatus { active: boolean; starting: boolean; sent: number; message: string; error: boolean }
export const monitorIdle: MonitorStatus = { active: false, starting: false, sent: 0, message: "Camera off", error: false };
export interface MonitorRegion { x0: number; y0: number; x1: number; y1: number }

/** One patient-bound camera session. Frames have no browser persistence and only one awaits admission. */
export class MonitorCapture {
  private stream?: MediaStream;
  private socket?: WebSocket;
  private timer?: number;
  private generation = 0;
  private state = { ...monitorIdle };
  private disposed = false;
  private waitingSince = 0;
  private video: HTMLVideoElement;
  private patient: string;
  private changed: (status: MonitorStatus) => void;
  constructor(video: HTMLVideoElement, patient: string, changed: (status: MonitorStatus) => void) {
    this.video = video; this.patient = patient; this.changed = changed;
  }
  private update(patch: Partial<MonitorStatus>) {
    this.state = { ...this.state, ...patch };
    if (!this.disposed) this.changed(this.state);
  }
  private async request(path: string, body: object) {
    const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ ...body, incident_id: this.patient }), signal: AbortSignal.timeout(5000) });
    if (!response.ok) throw new Error(`Camera request rejected (${response.status}). Check the active patient.`);
    return response.json();
  }
  async region(roi: MonitorRegion) {
    if (!(0 <= roi.x0 && roi.x0 < roi.x1 && roi.x1 <= 1 && 0 <= roi.y0 && roi.y0 < roi.y1 && roi.y1 <= 1)) {
      throw new Error("Select a nonempty monitor area within 0–100%.");
    }
    await this.request("/api/capture/roi", { ...roi, target: "monitor" });
  }
  async start(roi: MonitorRegion) {
    if (this.disposed || this.state.active || this.state.starting) return;
    const token = ++this.generation;
    this.update({ starting: true, error: false, message: "Allow camera access…" });
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error("Camera needs HTTPS or localhost.");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: { ideal: "environment" } } });
      if (token !== this.generation) { stream.getTracks().forEach((track) => track.stop()); return; }
      this.stream = stream; this.video.srcObject = stream;
      stream.getTracks().forEach((track) => { track.onended = () => this.stop("Camera disconnected. Restart when ready.", true); });
      await this.video.play();
      if (token !== this.generation) return;
      const socket = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/frames`);
      this.socket = socket;
      await new Promise<void>((resolve, reject) => {
        const timeout = window.setTimeout(() => { reject(new Error("Camera connection timed out.")); socket.close(); }, 5000);
        socket.onopen = () => { window.clearTimeout(timeout); resolve(); };
        socket.onerror = socket.onclose = () => { window.clearTimeout(timeout); reject(new Error("Camera connection unavailable; another camera may own this patient’s feed.")); };
      });
      if (token !== this.generation) return;
      socket.onclose = () => this.stop("Camera connection closed. Restart explicitly to resume.", true);
      socket.onerror = () => this.stop("Camera connection failed.", true);
      socket.onmessage = (event) => {
        this.waitingSince = 0;
        try {
          const reply = JSON.parse(event.data);
          if (reply.error) this.update({ message: reply.error, error: true });
          else this.update({ error: false, message: reply.gate?.usable === false
            ? "Frame skipped · adjust focus, lighting or monitor area"
            : "Watching · selected frames are read locally; verify proposed changes" });
        } catch { this.stop("Invalid camera response. Capture stopped.", true); }
      };
      await this.region(roi);
      if (token !== this.generation) return;
      const status = await this.request("/api/capture/auto", { on: true });
      if (token !== this.generation) return;
      this.update({ starting: false, active: true, message: "Watching · waiting for a usable monitor frame" });
      const tick = async () => {
        if (token !== this.generation) return;
        try { await this.frame(token); }
        catch (error) { this.stop(error instanceof Error ? error.message : "Frame capture failed", true); return; }
        if (token === this.generation) this.timer = window.setTimeout(tick, 1000 / Math.max(0.1, Math.min(1, status.fps_in || 1)));
      };
      await tick();
    } catch (error) {
      if (token === this.generation) this.stop(error instanceof Error ? error.message : "Camera unavailable", true);
    }
  }
  private async frame(token: number) {
    if (this.socket?.readyState !== WebSocket.OPEN) throw new Error("Camera connection lost.");
    if (this.waitingSince && Date.now() - this.waitingSince > 10000) throw new Error("Camera admission stopped responding.");
    if (this.waitingSince || this.socket.bufferedAmount > 1024 * 1024 || !this.video.videoWidth) return;
    const scale = Math.min(1, 1280 / Math.max(this.video.videoWidth, this.video.videoHeight));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(this.video.videoWidth * scale); canvas.height = Math.round(this.video.videoHeight * scale);
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Camera frame capture is unavailable.");
    context.drawImage(this.video, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", .8));
    if (token !== this.generation || !blob || blob.size > 1024 * 1024) return;
    if (this.socket?.readyState !== WebSocket.OPEN) return;
    this.waitingSince = Date.now(); this.socket.send(blob);
    this.update({ sent: this.state.sent + 1 });
  }
  stop(message = "Camera off · monitoring paused", error = false) {
    ++this.generation; window.clearTimeout(this.timer); this.waitingSince = 0;
    this.stream?.getTracks().forEach((track) => { track.onended = null; track.stop(); }); this.stream = undefined;
    if (this.socket) { this.socket.onclose = null; this.socket.onerror = null; this.socket.onmessage = null; this.socket.close(); this.socket = undefined; }
    this.video.srcObject = null;
    this.update({ active: false, starting: false, message, error });
  }
  dispose() { this.disposed = true; this.stop(); }
}
