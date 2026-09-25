import { readFileSync } from "node:fs";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
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
  it("starts listening and watching on its own in a live call", () => {
    render(<CabinApp />);
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalled();                       // a copilot, not a recorder to remember
    expect(screen.queryByRole("contentinfo")).toBeNull();                                // no capture footer
  });
  it("requests nothing when automatic capture is off, and offers one control to start", () => {
    useHerald.setState({ ui: initialUi("?capture=off") });
    render(<CabinApp />);
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Listen and watch" })).toBeTruthy();
    expect(screen.getByText(/Paused — tap to listen and watch/)).toBeTruthy();
    expect(screen.getByRole("region", { name: "How the patient is moving" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "What Herald did" })).toBeTruthy();
    expect(screen.queryByText(/Record only when authorized|processed on the vehicle/)).toBeNull();   // no disclaimers on Now
  });
  it("opens the county protocol search from the header", () => {
    render(<CabinApp />);
    fireEvent.click(screen.getByRole("button", { name: "Protocols" }));
    expect(screen.getByRole("dialog", { name: "County protocols" })).toBeTruthy();
  });
  it("exposes bounded push-to-talk and typed notes without starting the microphone", () => {
    useHerald.setState({ ui: initialUi("?capture=off") }); render(<CabinApp />);
    fireEvent.click(screen.getByRole("button", { name: "Type a note" }));
    expect(screen.getByRole("button", { name: /Hold to talk · medic/ })).toBeTruthy();
    expect(screen.getByLabelText("Spoken or typed note")).toBeTruthy();
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
  });
  it("opens the camera workspace without activating a device", () => {
    useHerald.setState({ ui: initialUi("?capture=off") }); render(<CabinApp />);
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
    expect(screen.queryByText("177")).toBeNull();          // an unconfirmed reading never appears as a documented value
    expect(screen.queryByText("Latest confirmed readings")?.closest("section")?.textContent ?? "").not.toContain("177");
  });
  it("disables capture in a replay", () => {
    useHerald.setState({ source: "fixture" }); render(<CabinApp />);
    expect((screen.getByRole("button", { name: "Listen and watch" }) as HTMLButtonElement).disabled).toBe(true);
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
    useHerald.setState({ ui: initialUi("?capture=off") });
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
