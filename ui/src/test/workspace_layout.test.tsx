import { readFileSync } from "node:fs";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WorkspaceCards, validOrder } from "@/features/cabin/WorkspaceCards";
import { CabinApp } from "@/features/cabin/CabinApp";
import { initialUi, useHerald } from "@/lib/store";
import { parseFixture } from "@/lib/ws";
import type { Snapshot } from "@/lib/types";

const cards = { capture: { label: "Capture", content: <p>Capture content</p> }, handoff: { label: "Handoff", content: <p>Handoff content</p> } };
const snapshot = (parseFixture(readFileSync("public/fixtures/stroke_demo.jsonl", "utf8"))[0].msg as { state: Snapshot }).state;
const order = () => screen.getAllByRole("article").map((item) => item.getAttribute("aria-label"));
beforeEach(() => { localStorage.clear(); useHerald.setState({ snapshot, source: "fixture", stale: false, conn: "open", ui: initialUi("") }); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("locked workspace layout", () => {
  it("rejects missing, unknown and duplicate stored cards", () => {
    for (const value of [null, ["capture"], ["capture", "capture"], ["patient-id", "handoff"]]) expect(validOrder(value)).toEqual(["capture", "handoff"]);
    expect(validOrder(["handoff", "capture"])).toEqual(["handoff", "capture"]);
  });
  it("requires explicit editing, supports move buttons, and saves only layout identifiers", () => {
    const view = render(<WorkspaceCards cards={cards} />);
    expect(screen.queryByRole("button", { name: /Drag Capture/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Arrange cards" }));
    fireEvent.click(screen.getByRole("button", { name: "Move Capture later" }));
    expect(order()).toEqual(["Handoff", "Capture"]);
    expect(localStorage.length).toBe(0);
    fireEvent.click(screen.getByRole("button", { name: "Save layout" }));
    expect(localStorage.getItem("herald.workspace-layout.v1")).toBe('["handoff","capture"]');
    view.unmount(); render(<WorkspaceCards cards={cards} />);
    expect(order()).toEqual(["Handoff", "Capture"]);
  });
  it("cancels draft changes and resets only when saved", () => {
    localStorage.setItem("herald.workspace-layout.v1", '["handoff","capture"]');
    render(<WorkspaceCards cards={cards} />);
    fireEvent.click(screen.getByRole("button", { name: "Arrange cards" }));
    fireEvent.click(screen.getByRole("button", { name: "Reset" }));
    expect(order()).toEqual(["Capture", "Handoff"]);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(order()).toEqual(["Handoff", "Capture"]);
  });
  it("handles unavailable storage without losing usable layout controls", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("disabled"); });
    render(<WorkspaceCards cards={cards} />);
    fireEvent.click(screen.getByRole("button", { name: "Arrange cards" }));
    fireEvent.click(screen.getByRole("button", { name: "Save layout" }));
    expect(screen.getByRole("status").textContent).toContain("could not save");
    expect(screen.getByRole("button", { name: "Arrange cards" })).toBeTruthy();
  });
  it("keeps keyboard focus in the layout controls when editing starts and ends", async () => {
    render(<WorkspaceCards cards={cards} />);
    fireEvent.click(screen.getByRole("button", { name: "Arrange cards" }));
    await act(async () => { await new Promise((resolve) => requestAnimationFrame(resolve)); });
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Reset" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await act(async () => { await new Promise((resolve) => requestAnimationFrame(resolve)); });
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Arrange cards" }));
  });
  it("supports pointer drop and discards a cancelled drag", () => {
    render(<WorkspaceCards cards={cards} />);
    fireEvent.click(screen.getByRole("button", { name: "Arrange cards" }));
    const handle = screen.getByRole("button", { name: /Drag Capture/ });
    handle.setPointerCapture = vi.fn();
    Object.defineProperty(document, "elementFromPoint", { configurable: true, value: vi.fn(() => screen.getByRole("article", { name: "Handoff" })) });
    const pointerDown = () => { const event = new Event("pointerdown", { bubbles: true }); Object.assign(event, { button: 0, pointerId: 1 }); fireEvent(handle, event); };
    pointerDown(); fireEvent.pointerMove(handle, { clientX: 500, clientY: 200 }); fireEvent.pointerCancel(handle);
    expect(order()).toEqual(["Capture", "Handoff"]);
    pointerDown(); fireEvent.pointerMove(handle, { clientX: 500, clientY: 200 }); fireEvent.pointerUp(handle);
    expect(order()).toEqual(["Handoff", "Capture"]);
  });
});

describe("component-focused ambulance view", () => {
  it("does not expose internal incident IDs or whole-page large view", () => {
    render(<CabinApp />);
    expect(screen.queryByRole("button", { name: "Large view" })).toBeNull();
    expect(document.body.textContent).not.toContain(snapshot.incident.id);
    expect(document.body.textContent).not.toContain(`…${snapshot.incident.id.slice(-4)}`);
  });
  it("restores focus to the originating card when returning to overview", async () => {
    render(<CabinApp />);
    const trigger = screen.getByRole("button", { name: "Handoff report" });
    trigger.focus(); fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("button", { name: "Back to now" }));
    await act(async () => { await new Promise((resolve) => requestAnimationFrame(resolve)); });
    expect(document.activeElement).toBe(trigger);
  });
  it("offers a direct automatic-camera stop and qualifies stale status", () => {
    useHerald.setState({ source: "live", stale: true, snapshot: { ...snapshot, capture: { auto: true, sees: "watching", pending: 0 } as NonNullable<Snapshot["capture"]> } });
    render(<CabinApp />);
    expect(screen.getByRole("button", { name: "Stop auto capture" })).toBeTruthy();
    // one honest line for the whole system: disconnected, showing the last known state
    expect(screen.getByText(/Offline — vehicle server disconnected, showing last state/)).toBeTruthy();
  });
  it("does not claim the camera is watching when its status is absent", () => {
    render(<CabinApp />);
    expect(screen.queryByText(/watching the monitor/)).toBeNull();
  });
  it("uses a reflowing layout for enlarged accessibility text", () => {
    useHerald.setState({ ui: { ...initialUi(""), typeScale: 1.5 } });
    const { container } = render(<CabinApp />);
    expect(container.querySelector(".cabin-large-text")).toBeTruthy();
  });
});
