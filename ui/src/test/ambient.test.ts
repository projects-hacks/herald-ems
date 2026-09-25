import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AmbientCapture, type AmbientStatus } from "@/features/cabin/ambient";
import { Endpointer } from "@/features/cabin/endpoint";
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
  const said = () => node.port.onmessage?.({ data: new Float32Array(16000).fill(0.1) });     // one second of speech
  const quiet = () => node.port.onmessage?.({ data: new Float32Array(16000) });               // one second of silence
  const block = () => { said(); quiet(); };                                                   // an utterance, ended by a pause
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
    await capture.start(); said();
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
    await capture.start(); said(); capture.dispose();
    expect(stop).toHaveBeenCalledOnce(); expect(fetch).not.toHaveBeenCalled();
  });
});

describe("speech endpointing", () => {
  const rate = 16000;
  const blocks = (seconds: number, level: number) => Array.from({ length: Math.round(seconds * 10) }, () => new Float32Array(rate / 10).fill(level));
  const feed = (e: Endpointer, bs: Float32Array[]) => bs.map((b) => e.push(b)).filter(Boolean) as Float32Array[][];
  it("sends nothing for silence or steady room noise", () => {
    const e = new Endpointer(rate);
    expect(feed(e, [...blocks(20, 0), ...blocks(20, 0.004)])).toEqual([]);
    expect(e.end()).toBeNull();
  });
  it("sends one utterance when the speaker pauses, with a little audio from before it", () => {
    const e = new Endpointer(rate);
    const out = feed(e, [...blocks(1, 0), ...blocks(2, 0.1), ...blocks(1, 0)]);
    expect(out).toHaveLength(1);
    const seconds = out[0].reduce((n, b) => n + b.length, 0) / rate;
    expect(seconds).toBeGreaterThan(2.7); expect(seconds).toBeLessThan(3.2);
  });
  it("does not send a cough-length burst", () => {
    const e = new Endpointer(rate);
    expect(feed(e, [...blocks(1, 0), ...blocks(0.2, 0.2), ...blocks(1.5, 0)])).toEqual([]);
  });
  it("cuts a long monologue so no clip exceeds Whisper's window", () => {
    const e = new Endpointer(rate);
    const out = feed(e, blocks(40, 0.1));
    expect(out.length).toBeGreaterThanOrEqual(2);
    for (const u of out) expect(u.reduce((n, b) => n + b.length, 0) / rate).toBeLessThanOrEqual(15.1);
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
