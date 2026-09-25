// The clinical-severity treatment on the medic screen (owner sign-off 2026-09-25): an abnormal value shows as
// abnormal even when it is not changing, and the signal is never colour alone. Severity is backend-computed
// (config/vital_ranges.yaml); these tests assert the UI renders what the snapshot carries.
import { readFileSync } from "node:fs";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CabinApp } from "@/features/cabin/CabinApp";
import { initialUi, useHerald } from "@/lib/store";
import { parseFixture } from "@/lib/ws";
import type { Snapshot } from "@/lib/types";

const base = (parseFixture(readFileSync("public/fixtures/stroke_demo.jsonl", "utf8"))[0].msg as { state: Snapshot }).state;
vi.mock("@/lib/contract", () => ({ useContract: () => ({ keys: {}, relayTiers: {}, changeRules: {} }) }));

function fact(over: Partial<Snapshot["facts"][string]>): Snapshot["facts"][string] {
  return { id: "f", key: "vitals.spo2", label: "SpO2", value: 84, unit: "%", status: "confirmed",
    ts: new Date().toISOString(), captured_by: "device", provenance: {}, role: "medic", speaker: null,
    confidence: 1, previous_value: null, previous_ts: null, ...over } as Snapshot["facts"][string];
}

function openTrends(snapshot: Snapshot) {
  useHerald.setState({ snapshot, source: "live", stale: false, conn: "open", ui: initialUi("") });
  render(<CabinApp />);
  fireEvent.click(screen.getByRole("button", { name: "Record" }));
  fireEvent.click(screen.getByRole("tab", { name: "Trends & scores" }));
}

describe("vital severity on the medic screen", () => {
  beforeEach(() => { Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn() } }); });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it("shows a word beside a critical value, so it is never colour alone", () => {
    openTrends({ ...base, facts: { "vitals.spo2": fact({ severity: "critical" }) }, changed: [] });
    const panel = screen.getByText("Latest confirmed readings").closest("section")!;
    expect(panel.textContent).toContain("critical");     // the WORD, not just a colour
    expect(panel.textContent).toContain("84");
  });

  it("shows 'out of range' for an abnormal value", () => {
    openTrends({ ...base, facts: { "vitals.hr": fact({ key: "vitals.hr", label: "Heart rate", value: 104, unit: "/min", severity: "abnormal" }) }, changed: [] });
    expect(screen.getByText("Latest confirmed readings").closest("section")!.textContent).toContain("out of range");
  });

  it("gives a normal value no severity word at all", () => {
    openTrends({ ...base, facts: { "vitals.sbp": fact({ key: "vitals.sbp", label: "Systolic BP", value: 118, unit: "mmHg" }) }, changed: [] });
    const panel = screen.getByText("Latest confirmed readings").closest("section")!;
    expect(panel.textContent).toContain("118");
    expect(panel.textContent).not.toContain("critical");
    expect(panel.textContent).not.toContain("out of range");
  });

  it("flags an abnormal-but-stable trend that did not move (severity without significant)", () => {
    // SpO2 84 -> 84: no change, so `significant` is false and there is no "big change" badge, but it is critical.
    openTrends({ ...base, facts: {}, changed: [{
      key: "vitals.spo2", label: "SpO2", series: [84, 84], times: [new Date().toISOString(), new Date().toISOString()],
      delta: 0, direction: "flat", significant: false, severity: "critical",
    }] });
    const card = screen.getByLabelText("SpO2, critical");
    expect(card.textContent).toContain("critical");
    expect(card.textContent).not.toContain("big change");   // it did not move
  });

  it("announces the newest confirmed reading in a polite live region", () => {
    openTrends({ ...base, facts: { "vitals.spo2": fact({ severity: "critical" }) }, changed: [] });
    const live = document.querySelector('[role="status"][aria-live="polite"]');
    expect(live?.textContent).toContain("SpO2");
    expect(live?.textContent).toContain("critical");
  });

  it("marks a monitor-read value with its source, not only in the Facts tab", () => {
    openTrends({ ...base, facts: { "vitals.spo2": fact({ captured_by: "device", severity: "critical" }) }, changed: [] });
    expect(screen.getByText("Latest confirmed readings").closest("section")!.querySelector('[aria-label="monitor"]')).toBeTruthy();
  });
});
