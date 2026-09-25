import { readFileSync } from "node:fs";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CabinApp } from "@/features/cabin/CabinApp";
import { CameraCapture } from "@/features/cabin/CameraCapture";
import { initialUi, useHerald } from "@/lib/store";
import { parseFixture } from "@/lib/ws";
import type { Snapshot } from "@/lib/types";

const snapshot = (parseFixture(readFileSync("public/fixtures/stroke_demo.jsonl", "utf8"))[0].msg as { state: Snapshot }).state;
vi.mock("@/lib/contract", () => ({ useContract: () => ({ keys: {}, relayTiers: {}, changeRules: {} }) }));

describe("ambulance workspace", () => {
  beforeEach(() => {
    useHerald.setState({ snapshot, source: "live", stale: false, conn: "open", ui: initialUi("") });
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn() } });
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });
  it("opens with explicit microphone off and never requests devices automatically", () => {
    render(<CabinApp />);
    expect(screen.getByRole("button", { name: "Start listening" })).toBeTruthy();
    expect(screen.getByText("Microphone off")).toBeTruthy();
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
    expect(screen.getByRole("region", { name: "Latest documented readings" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Agentic camera capture" })).toBeTruthy();
    expect(screen.getByRole("status", { name: "Vehicle and ED status" })).toBeTruthy();
    expect(screen.getByText("Mass-casualty · add patient")).toBeTruthy();
  });
  it("exposes bounded push-to-talk and typed notes without starting the microphone", () => {
    render(<CabinApp />);
    fireEvent.click(screen.getByRole("button", { name: "Type a note" }));
    expect(screen.getByRole("button", { name: /Hold to talk · medic/ })).toBeTruthy();
    expect(screen.getByLabelText("Spoken or typed note")).toBeTruthy();
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
  });
  it("opens camera details without activating the camera and keeps capture controls visible", () => {
    render(<CabinApp />);
    fireEvent.click(screen.getByRole("button", { name: "Camera" }));
    expect(screen.getByRole("heading", { name: "Capture visual evidence" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Start listening" })).toBeTruthy();
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Close details" }));
    expect(screen.queryByRole("heading", { name: "Capture visual evidence" })).toBeNull();
  });
  it("never promotes an unverified reading into the glanceable value", () => {
    useHerald.setState({ snapshot: { ...snapshot, facts: { ...snapshot.facts, "vitals.hr": {
      id: "pending", key: "vitals.hr", label: "Heart rate", value: 177, unit: "bpm", status: "unconfirmed", ts: new Date().toISOString(),
    } as Snapshot["facts"][string] } } });
    render(<CabinApp />);
    const readings = within(screen.getByRole("region", { name: "Latest documented readings" }));
    expect(readings.queryByText("177")).toBeNull();
    expect(readings.getByText(/Needs verification/)).toBeTruthy();
  });
  it("disables capture in a replay", () => {
    useHerald.setState({ source: "fixture" }); render(<CabinApp />);
    expect((screen.getByRole("button", { name: "Start listening" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Camera" }) as HTMLButtonElement).disabled).toBe(true);
  });
  it("camera permission completing after panel close cannot leave a live stream", async () => {
    let resolve!: (stream: MediaStream) => void;
    const promise = new Promise<MediaStream>((done) => { resolve = done; });
    vi.mocked(navigator.mediaDevices.getUserMedia).mockReturnValue(promise);
    const stop = vi.fn(); const view = render(<CameraCapture />);
    fireEvent.click(screen.getByRole("button", { name: "Open camera" })); view.unmount();
    await act(async () => { resolve({ getTracks: () => [{ stop }] } as unknown as MediaStream); await promise; });
    expect(stop).toHaveBeenCalledOnce();
  });
  it("offers a file picker alternative to dropping a photo", () => {
    render(<CameraCapture />);
    expect(screen.getByLabelText("Choose photo")).toBeTruthy();
  });
});
