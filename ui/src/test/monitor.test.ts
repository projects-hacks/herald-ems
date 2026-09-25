import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MonitorCapture, type MonitorStatus } from "@/features/capture/monitor";

class Socket {
  static OPEN = 1;
  static instances: Socket[] = [];
  readyState = 1; bufferedAmount = 0;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  send = vi.fn(); close = vi.fn(() => { this.readyState = 3; this.onclose?.(); });
  constructor() { Socket.instances.push(this); queueMicrotask(() => this.onopen?.()); }
}
let capture: MonitorCapture, states: MonitorStatus[], stop: ReturnType<typeof vi.fn>;
const roi = { x0: 0, y0: 0, x1: 1, y1: 1 };
const settle = async () => { for (let i = 0; i < 15; i++) await Promise.resolve(); };
beforeEach(() => {
  vi.useFakeTimers(); Socket.instances = []; states = []; stop = vi.fn();
  vi.stubGlobal("WebSocket", Socket);
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop, onended: null }] })) } });
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({ fps_in: 1 }) })));
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ drawImage: vi.fn() } as unknown as CanvasRenderingContext2D);
  vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation((callback) => callback(new Blob(["frame"], { type: "image/jpeg" })));
  const video = { videoWidth: 1280, videoHeight: 720, srcObject: null, play: async () => {} } as unknown as HTMLVideoElement;
  capture = new MonitorCapture(video, "patient-one", (state) => states.push(state));
});
afterEach(() => { capture.dispose(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it("requires one explicit start and sends bounded frames for that patient until stopped", async () => {
  expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
  await capture.start(roi);
  const socket = Socket.instances[0];
  expect(states.at(-1)?.active).toBe(true);
  expect(socket.send).toHaveBeenCalledTimes(1);
  expect(fetch).toHaveBeenCalledWith("/api/capture/auto", expect.objectContaining({ body: JSON.stringify({ on: true, incident_id: "patient-one" }) }));
  await vi.advanceTimersByTimeAsync(3000);
  expect(socket.send).toHaveBeenCalledTimes(1); // one unacknowledged frame, never an accumulating queue
  socket.onmessage?.({ data: JSON.stringify({ accepted: true, gate: { usable: true } }) });
  await vi.advanceTimersByTimeAsync(1000);
  expect(socket.send).toHaveBeenCalledTimes(2);
  capture.stop(); await vi.advanceTimersByTimeAsync(5000);
  expect(socket.send).toHaveBeenCalledTimes(2); expect(stop).toHaveBeenCalledOnce();
});

it("discards a camera permission result after patient disposal without opening a socket", async () => {
  let resolve!: (stream: MediaStream) => void;
  vi.mocked(navigator.mediaDevices.getUserMedia).mockReturnValue(new Promise((done) => { resolve = done; }));
  const request = capture.start(roi); capture.dispose();
  resolve({ getTracks: () => [{ stop }] } as unknown as MediaStream); await request;
  expect(stop).toHaveBeenCalledOnce(); expect(Socket.instances).toHaveLength(0); expect(fetch).not.toHaveBeenCalled();
});

it("stops visibly when admission stalls instead of keeping a false watching state", async () => {
  await capture.start(roi); await vi.advanceTimersByTimeAsync(12000);
  expect(states.at(-1)).toMatchObject({ active: false, error: true });
  expect(states.at(-1)?.message).toContain("stopped responding"); expect(stop).toHaveBeenCalledOnce();
});

it("rejects an invalid region and a server-refused patient without retaining the device", async () => {
  await capture.start({ ...roi, x1: 0 });
  expect(states.at(-1)).toMatchObject({ active: false, error: true }); expect(stop).toHaveBeenCalledOnce();
  expect(fetch).not.toHaveBeenCalled();
  vi.mocked(fetch).mockResolvedValue({ ok: false, status: 409 } as Response);
  await capture.start(roi); await settle();
  expect(states.at(-1)?.message).toContain("409"); expect(stop).toHaveBeenCalledTimes(2);
});
