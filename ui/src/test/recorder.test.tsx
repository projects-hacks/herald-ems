import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { useHerald } from "@/lib/store";
import { useRecorder } from "@/features/capture/useRecorder";
import { encodeWav } from "@/features/capture/pcm";

afterEach(() => vi.unstubAllGlobals());
it("release during the permission prompt stops late microphone tracks without sending", async () => {
  const snapshot = JSON.parse(readFileSync("src/test/fixtures/live_every_call.json", "utf8"));
  useHerald.setState({ snapshot, source: "live", conn: "open", stale: false });
  let resolve!: (value: MediaStream) => void;
  const stopped = vi.fn();
  const stream = { getTracks: () => [{ stop: stopped }] } as unknown as MediaStream;
  const permission = new Promise<MediaStream>((done) => { resolve = done; });
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: vi.fn(() => permission) } });
  vi.stubGlobal("fetch", vi.fn());
  const { result, unmount } = renderHook(useRecorder);
  let starting!: Promise<void>;
  act(() => { starting = result.current.start("medic"); });
  await act(() => result.current.stop());
  await act(async () => { resolve(stream); await starting; });
  expect(stopped).toHaveBeenCalledOnce(); expect(fetch).not.toHaveBeenCalled(); unmount();
});
it("encodes bounded mono PCM at 16 kHz with clipping", async () => {
  const blob = encodeWav([new Float32Array([2, -2, 0, 1])], 16000);
  const buffer = await new Promise<ArrayBuffer>((resolve) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result as ArrayBuffer); reader.readAsArrayBuffer(blob); });
  const view = new DataView(buffer);
  expect(view.getUint32(24, true)).toBe(16000); expect(view.getUint16(22, true)).toBe(1);
  expect(view.getInt16(44, true)).toBe(32767); expect(view.getInt16(46, true)).toBe(-32768);
});

it("releases hardware and submits a WAV with the starting patient and speaker", async () => {
  const snapshot = JSON.parse(readFileSync("src/test/fixtures/live_every_call.json", "utf8"));
  useHerald.setState({ snapshot, source: "live", conn: "open", stale: false });
  const stop = vi.fn(), close = vi.fn(), disconnect = vi.fn();
  const node = { onaudioprocess: null as ((e: unknown) => void) | null, connect: vi.fn(), disconnect };
  class FakeAudioContext {
    sampleRate = 48000; destination = {}; close = close;
    resume = async () => {};
    createMediaStreamSource = () => ({ connect: vi.fn(), disconnect });
    createScriptProcessor = () => node;
  }
  vi.stubGlobal("AudioContext", FakeAudioContext);
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: async () => ({ getTracks: () => [{ stop }] }) } });
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({}) })));
  const { result, unmount } = renderHook(useRecorder);
  await act(() => result.current.start("other", "daughter"));
  node.onaudioprocess?.({ inputBuffer: { getChannelData: () => new Float32Array(4096) } });
  await act(() => result.current.stop());
  expect(stop).toHaveBeenCalled(); expect(close).toHaveBeenCalled(); expect(disconnect).toHaveBeenCalled();
  expect(fetch).toHaveBeenCalledWith("/api/audio", expect.objectContaining({ headers: { "X-Herald-Patient": snapshot.incident.id } }));
  const body = vi.mocked(fetch).mock.calls[0][1]!.body as FormData;
  expect(body.get("speaker")).toBe("daughter"); expect(body.get("captured_by")).toBe("other");
  expect((body.get("file") as File).type).toBe("audio/wav"); unmount();
});
