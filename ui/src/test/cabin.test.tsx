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
    expect(screen.getByText("Not listening")).toBeTruthy();   // the presence pill is the whole system status
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
    expect(screen.getByRole("region", { name: "How the patient is moving" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Herald is doing" })).toBeTruthy();
    // controls only in the dock: no status prose, no disclaimers
    const dock = within(screen.getByRole("contentinfo"));
    expect(dock.queryByText(/camera/i, { selector: "p, span, small" })).toBeNull();
    expect(dock.queryByText(/Microphone off|Record only when authorized|processed on the vehicle/)).toBeNull();
  });
  it("opens the county protocol search from the header", () => {
    render(<CabinApp />);
    fireEvent.click(screen.getByRole("button", { name: "Protocols" }));
    expect(screen.getByRole("dialog", { name: "County protocols" })).toBeTruthy();
  });
  it("exposes bounded push-to-talk and typed notes without starting the microphone", () => {
    render(<CabinApp />);
    fireEvent.click(screen.getByRole("button", { name: "Type" }));
    expect(screen.getByRole("button", { name: /Hold to talk · medic/ })).toBeTruthy();
    expect(screen.getByLabelText("Spoken or typed note")).toBeTruthy();
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
  });
  it("opens the camera workspace without activating a device", () => {
    render(<CabinApp />);
    fireEvent.click(screen.getByRole("button", { name: "Camera" }));
    expect(screen.getByRole("heading", { name: "Capture visual evidence" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Start listening" })).toBeTruthy();
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Back to now" }));
    expect(screen.queryByRole("heading", { name: "Capture visual evidence" })).toBeNull();
  });
  it("never promotes an unverified reading into the glanceable value", () => {
    useHerald.setState({ snapshot: { ...snapshot, facts: { ...snapshot.facts, "vitals.hr": {
      id: "pending", key: "vitals.hr", label: "Heart rate", value: 177, unit: "bpm", status: "unconfirmed", ts: new Date().toISOString(), provenance: {},
    } as Snapshot["facts"][string] } } });
    render(<CabinApp />);
    fireEvent.click(screen.getByRole("button", { name: "Record" }));
    fireEvent.click(screen.getByRole("tab", { name: "Trends & scores" }));
    const readings = within(screen.getByRole("region", { name: "Latest documented readings" }));
    expect(readings.queryByText("177")).toBeNull();
    expect(readings.getByText(/Needs verification/)).toBeTruthy();
  });
  it("disables capture in a replay", () => {
    useHerald.setState({ source: "fixture" }); render(<CabinApp />);
    expect((screen.getByRole("button", { name: "Start listening" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Camera" }));
    expect((screen.getByRole("button", { name: "Start monitor watch" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "Close details" })).toBeNull();
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
  it("stops a pending permission request when switching capture methods", async () => {
    let resolve!: (stream: MediaStream) => void;
    const request = new Promise<MediaStream>((done) => { resolve = done; });
    vi.mocked(navigator.mediaDevices.getUserMedia).mockReturnValue(request);
    const stop = vi.fn();
    render(<CabinApp />);
    fireEvent.click(screen.getByRole("button", { name: "Camera" }));
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Take a photo" }), { button: 0, ctrlKey: false });
    fireEvent.click(screen.getByRole("button", { name: "Open camera" }));
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Connected camera" }), { button: 0, ctrlKey: false });
    await act(async () => { resolve({ getTracks: () => [{ stop }] } as unknown as MediaStream); await request; });
    expect(stop).toHaveBeenCalledOnce();
    expect(screen.queryByRole("button", { name: "Capture photo" })).toBeNull();
    expect(screen.getByRole("button", { name: "Enable auto capture" })).toBeTruthy();
  });
  it.each(["Record"])("explains unavailable patient data on %s", (name) => {
    useHerald.setState({ snapshot: null, conn: "closed" });
    render(<CabinApp />);
    fireEvent.click(screen.getByRole("button", { name }));
    expect(screen.getByText(/Patient data is not available yet/)).toBeTruthy();
    expect(screen.queryByText("No open review items")).toBeNull();
    expect(screen.queryByRole("button", { name: "Close details" })).toBeNull();
  });
  it("offers a file picker alternative to dropping a photo", () => {
    render(<CameraCapture />);
    expect(screen.getByLabelText("Choose photo")).toBeTruthy();
  });
});
