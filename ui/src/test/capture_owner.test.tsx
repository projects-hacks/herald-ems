// One Herald tab captures at a time (features/cabin/captureOwner.ts): a second tab listening to the same cabin
// uploaded every sentence twice, and its camera was refused by the server every 4 s.
import { readFileSync } from "node:fs";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CabinApp } from "@/features/cabin/CabinApp";
import { initialUi, useHerald } from "@/lib/store";
import { initialCaptureElsewhere } from "@/features/cabin/captureOwner";
import { parseFixture } from "@/lib/ws";
import type { Snapshot } from "@/lib/types";

const snapshot = (parseFixture(readFileSync("public/fixtures/stroke_demo.jsonl", "utf8"))[0].msg as { state: Snapshot }).state;
vi.mock("@/lib/contract", () => ({ useContract: () => ({ keys: {}, relayTiers: {}, changeRules: {} }) }));

const locks = (held: boolean) => ({ request: vi.fn((_name: string, _opts: object, cb: () => Promise<void>) =>
  held ? new Promise(() => {}) : cb()) });                   // held elsewhere: the callback never runs

describe("one capturing tab", () => {
  beforeEach(() => {
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn(() => new Promise(() => {})) } });
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); Reflect.deleteProperty(navigator, "locks"); });
  it("a tab that gets the lock listens and watches", () => {
    Object.defineProperty(navigator, "locks", { configurable: true, value: locks(false) });
    useHerald.setState({ snapshot, source: "live", stale: false, conn: "open", captureElsewhere: initialCaptureElsewhere(), ui: initialUi("") });
    render(<CabinApp />);
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalled();
  });
  it("a second tab opens neither microphone nor camera, and says where Herald is listening", () => {
    Object.defineProperty(navigator, "locks", { configurable: true, value: locks(true) });
    useHerald.setState({ snapshot, source: "live", stale: false, conn: "open", captureElsewhere: initialCaptureElsewhere(), ui: initialUi("") });
    render(<CabinApp />);
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
    expect(screen.getByText(/Listening and watching in another Herald tab/)).toBeTruthy();
  });
});
