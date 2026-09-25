import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AmbientCapture, type AmbientStatus } from "@/features/cabin/ambient";
import { join, wav } from "@/features/cabin/pcm";

describe("continuous capture", () => {
  let stop: ReturnType<typeof vi.fn>;
  let node: { port: { onmessage: ((e: { data: Float32Array }) => void) | null }; connect: () => void; disconnect: () => void };
  let states: AmbientStatus[];
  let capture: AmbientCapture;
  beforeEach(() => {
    states = []; stop = vi.fn();
    node = { port: { onmessage: null }, connect: vi.fn(), disconnect: vi.fn() };
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: {
      getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop }], getAudioTracks: () => [] })),
    } });
    vi.stubGlobal("AudioContext", class {
      sampleRate = 16000;
      audioWorklet = { addModule: vi.fn(async () => {}) };
      createGain() { return { gain: { value: 1 }, connect: vi.fn() }; }
      createMediaStreamSource() { return { connect: vi.fn() }; }
      resume = vi.fn(async () => {}); close = vi.fn(async () => {});
    });
    vi.stubGlobal("AudioWorkletNode", class { constructor() { return node; } });
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({}) })));
    capture = new AmbientCapture("patient-1", (s) => states.push(s));
  });
  afterEach(() => { capture.dispose(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  const block = () => node.port.onmessage?.({ data: new Float32Array(128000).fill(0.1) });
  const settle = async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); };

  it("does not capture until explicitly started", () => {
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("sends multiple clips without another press, bound to patient and unverified source", async () => {
    await capture.start(); block(); await settle(); block(); await settle();
    expect(fetch).toHaveBeenCalledTimes(2);
    const form = vi.mocked(fetch).mock.calls[0][1]?.body as FormData;
    expect(form.get("incident_id")).toBe("patient-1");
    expect(form.get("ambient")).toBe("true");
    expect(form.get("captured_by")).toBe("other");
    expect(states.at(-1)?.listening).toBe(true);
  });
  it("stops tracks and flushes a partial clip on pause", async () => {
    await capture.start(); node.port.onmessage?.({ data: new Float32Array(16000) });
    capture.pause(); await settle();
    expect(stop).toHaveBeenCalledOnce();
    expect(fetch).toHaveBeenCalledOnce();
    expect(states.at(-1)?.listening).toBe(false);
  });
  it("releases a permission result that arrives after cancellation", async () => {
    let resolve!: (s: MediaStream) => void;
    vi.mocked(navigator.mediaDevices.getUserMedia).mockReturnValue(new Promise((r) => { resolve = r; }));
    const started = capture.start(); capture.pause();
    resolve({ getTracks: () => [{ stop }] } as unknown as MediaStream); await started;
    expect(stop).toHaveBeenCalledOnce(); expect(fetch).not.toHaveBeenCalled();
  });
  it("stops with an explicit error instead of silently building an unbounded queue", async () => {
    vi.mocked(fetch).mockReturnValue(new Promise(() => {}));
    await capture.start(); block(); block(); block(); block();
    expect(states.at(-1)).toMatchObject({ listening: false, error: true });
    expect(states.at(-1)?.message).toContain("unsent clip was discarded");
    expect(fetch).toHaveBeenCalledOnce();
  });
  it("does not keep recording after a server error", async () => {
    vi.mocked(fetch).mockResolvedValue({ ok: false, status: 503 } as Response);
    await capture.start(); block(); await settle();
    expect(states.at(-1)).toMatchObject({ listening: false, error: true });
    expect(stop).toHaveBeenCalledOnce();
  });
  it("discards unsent audio on dispose, without starting another upload", async () => {
    await capture.start(); node.port.onmessage?.({ data: new Float32Array(16000) }); capture.dispose();
    expect(stop).toHaveBeenCalledOnce(); expect(fetch).not.toHaveBeenCalled();
  });
});

describe("PCM encoding", () => {
  it("joins without gaps and returns a mono WAV payload", () => {
    const samples = join([new Float32Array([0, 0.5]), new Float32Array([-0.5, 1])]);
    expect([...samples]).toEqual([0, 0.5, -0.5, 1]);
    const payload = wav(samples, 16000);
    expect(payload.type).toBe("audio/wav"); expect(payload.size).toBe(52);
  });
});
