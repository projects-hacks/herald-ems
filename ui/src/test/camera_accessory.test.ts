import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { afterEach, describe, expect, it, vi } from "vitest";

const script = readFileSync("../web/continuous.js", "utf8");
const html = readFileSync("../web/capture.html", "utf8");
afterEach(() => { document.body.innerHTML = ""; vi.restoreAllMocks(); });

function accessory() {
  document.body.innerHTML = html;
  const request = vi.fn();
  const context = { document, window, fetch: request, setInterval: vi.fn(), clearTimeout: vi.fn() };
  const api = runInNewContext(script + `
    ({stop, own: (stream, ws) => { media = stream; socket = ws; }})`, context);
  return { ...api, request };
}

describe("standalone camera ownership", () => {
  it("hiding an idle accessory never issues a global capture stop", () => {
    const { request } = accessory();
    Object.defineProperty(document, "hidden", { configurable: true, get: () => true });
    document.dispatchEvent(new Event("visibilitychange"));
    expect(request).not.toHaveBeenCalled();
  });
  it("Stop releases its own tracks and socket without changing another source through HTTP", () => {
    const { own, stop, request } = accessory();
    const track = { stop: vi.fn(), onended: vi.fn() };
    const socket = { close: vi.fn(), onclose: vi.fn() };
    own({ getTracks: () => [track] }, socket);
    stop();
    expect(track.stop).toHaveBeenCalledOnce();
    expect(socket.close).toHaveBeenCalledOnce();
    expect(request).not.toHaveBeenCalled();
  });
});
