import { readFileSync } from "node:fs";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TranscriptBar } from "@/layout/TranscriptBar";
import { initialUi, useHerald } from "@/lib/store";
import { parseFixture } from "@/lib/ws";
import type { Snapshot } from "@/lib/types";

const snapshot = (parseFixture(readFileSync("public/fixtures/stroke_demo.jsonl", "utf8"))[0].msg as { state: Snapshot }).state;
vi.mock("@/lib/contract", () => ({ useContract: () => ({ keys: {}, relayTiers: {}, changeRules: {} }) }));

describe("capture interaction safety", () => {
  beforeEach(() => {
    useHerald.setState({ snapshot, source: "live", stale: false, conn: "open", ui: initialUi("") });
    HTMLElement.prototype.setPointerCapture = vi.fn();
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });
  it("stops the microphone when release happens before permission resolves", async () => {
    let resolve!: (stream: MediaStream) => void;
    const request = new Promise<MediaStream>((done) => { resolve = done; });
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn(() => request) } });
    const stop = vi.fn();
    render(<TranscriptBar />);
    const button = screen.getByRole("button", { name: /Hold to talk · medic/ });
    fireEvent.pointerDown(button);
    fireEvent.pointerUp(button);
    await act(async () => { resolve({ getTracks: () => [{ stop }] } as unknown as MediaStream); await request; });
    expect(stop).toHaveBeenCalledOnce();
    expect(useHerald.getState().ui.heldAlerts).toBe(false);
  });
  it("never starts background recording from Space on another button or a dialog", () => {
    const getUserMedia = vi.fn();
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia } });
    render(<TranscriptBar />);
    fireEvent.keyDown(screen.getByRole("button", { name: "Manual entry" }), { code: "Space", key: " " });
    expect(getUserMedia).not.toHaveBeenCalled();
    const dialog = document.createElement("div"); dialog.setAttribute("role", "dialog"); document.body.append(dialog);
    fireEvent.keyDown(document.body, { code: "Space", key: " " });
    expect(getUserMedia).not.toHaveBeenCalled(); dialog.remove();
  });
  it("disables writes while disconnected", () => {
    useHerald.setState({ stale: true, conn: "closed" });
    render(<TranscriptBar />);
    expect((screen.getByRole("button", { name: /Hold to talk · medic/ }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Manual entry" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
