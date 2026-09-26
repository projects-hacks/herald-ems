// Readings the camera takes from the patient monitor are device readings (owner's decision, 2026-09-26): the server
// records them confirmed (role "device", captured_by "camera"), so they never ask the medic for a tap, and they show
// in the trends marked as from the monitor. A reading the capture agent held (an implausible jump) still waits, with
// its reason. These tests assert the screens render what the snapshot carries.
import { readFileSync } from "node:fs";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CabinApp } from "@/features/cabin/CabinApp";
import { readingCards } from "@/lib/copilot";
import { fromMonitor } from "@/lib/format";
import { attention, needsTap } from "@/lib/selectors";
import { initialUi, useHerald } from "@/lib/store";
import { parseFixture } from "@/lib/ws";
import type { Changed, FactView, Snapshot } from "@/lib/types";
import { monitorShare } from "@/pages/TrendsPage";

const base = (parseFixture(readFileSync("public/fixtures/stroke_demo.jsonl", "utf8"))[0].msg as { state: Snapshot }).state;
vi.mock("@/lib/contract", () => ({ useContract: () => ({ keys: {}, relayTiers: {}, changeRules: {} }) }));

const T = "2026-09-26T02:06:30+00:00";
function reading(key: string, label: string, value: number, over: Partial<FactView> = {}): FactView {
  return { id: `m-${key}`, key, label, value, unit: null, status: "confirmed", ts: T, captured_by: "camera", role: "device",
    speaker: "monitor", confidence: 0.9, previous_value: null, previous_ts: null,
    provenance: { frame_id: "fr1", photo_id: "p1", trigger: "monitor_changed", auto: true, crop: [0, 0, 1, 1] },
    ...over } as FactView;
}
const monitorFacts = {
  "vitals.hr": reading("vitals.hr", "Heart rate", 130),
  "vitals.sbp": reading("vitals.sbp", "Systolic BP", 85),
  "vitals.spo2": reading("vitals.spo2", "SpO2", 90),
  "vitals.etco2": reading("vitals.etco2", "EtCO2 (mmHg)", 22),
};
const sbpTrend: Changed = {
  key: "vitals.sbp", label: "Systolic BP", series: [104, 96, 85], times: [T, T, T], delta: -19, direction: "down",
  significant: true, unconfirmed: false, unconfirmed_fact_ids: [], confirmed: [true, true, true], from_monitor: [true, true, true],
};
const snap = (over: Partial<Snapshot> = {}): Snapshot =>
  ({ ...base, facts: monitorFacts, changed: [sbpTrend], alerts: [], capture_groups: [], events: {}, ...over });

function show(snapshot: Snapshot) {
  useHerald.setState({ snapshot, source: "live", stale: false, conn: "open", ui: initialUi("") });
  render(<CabinApp />);
}

describe("monitor readings on the medic screen", () => {
  beforeEach(() => { Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn() } }); });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it("knows a camera read of the monitor from a photo", () => {
    expect(fromMonitor(monitorFacts["vitals.hr"])).toBe(true);
    expect(fromMonitor({ captured_by: "camera", role: "photo" })).toBe(false);
    expect(fromMonitor({ captured_by: "device", role: "device" })).toBe(true);
    expect(fromMonitor({ captured_by: "medic", role: "medic" })).toBe(false);
  });

  it("asks for no tap on an auto-confirmed monitor reading", () => {
    const s = snap();
    expect(needsTap(s)).toEqual([]);
    expect(readingCards(s)).toEqual([]);
    expect(attention(s, {}).confirmFacts).toEqual([]);
    show(s);
    const needs = screen.getByRole("region", { name: /Needs you/ });
    expect(needs.textContent).not.toMatch(/Heart rate|SpO2|EtCO2|Systolic/);
    expect(within(needs).queryByRole("button", { name: /Confirm/ })).toBeNull();
  });

  it("still asks about a reading the capture agent held, and says why", () => {
    const why = "Monitor read SpO2 49, 45 from 94 15 s earlier: check the monitor, then confirm or correct";
    const held = reading("vitals.spo2", "SpO2", 49, { id: "held", status: "unconfirmed", provenance: {
      frame_id: "fr2", photo_id: "p2", trigger: "monitor_changed", auto: true, hold_reason: why } as FactView["provenance"] });
    const s = snap({ facts: { ...monitorFacts, "vitals.spo2": held },
      capture_groups: [{ frame_id: "fr2", trigger: "monitor_changed", photo_id: "p2", ts: T, batch_fact_ids: [],
        individual: [{ id: "held", key: "vitals.spo2", label: "SpO2", reason: "held fact requires individual review" }] }] });
    expect(needsTap(s).map((f) => f.id)).toEqual(["held"]);
    show(s);
    const needs = screen.getByRole("region", { name: /Needs you/ });
    expect(needs.textContent).toContain("49");
    expect(needs.textContent).toContain(why);
  });

  it("marks a movement row read off the monitor", () => {
    show(snap());
    const movement = screen.getByRole("region", { name: "How the patient is moving" });
    expect(movement.textContent).toContain("Systolic BP 104 → 96 → 85");
    expect(movement.textContent).toContain("from the monitor");
    expect(movement.textContent).not.toContain("Unconfirmed reading");
    expect(within(movement).queryByRole("button", { name: /Confirm/ })).toBeNull();
  });

  it("names the first and the latest readings of a long monitor trend, not every point", () => {
    const long = { ...sbpTrend, series: [110, 108, 106, 104, 102, 100, 98, 96, 94], times: Array(9).fill(T),
      confirmed: Array(9).fill(true), from_monitor: Array(9).fill(true) };
    show(snap({ changed: [long] }));
    const movement = screen.getByRole("region", { name: "How the patient is moving" });
    expect(movement.textContent).toContain("Systolic BP 110 → … → 98 → 96 → 94");
  });

  it("shows confirmed monitor readings on the Trends tab, from the monitor", () => {
    const hr: Changed = { key: "vitals.hr", label: "Heart rate", series: [116, 126, 130], times: [T, T, T], delta: 14,
      direction: "up", significant: false, confirmed: [true, true, true], from_monitor: [true, true, true] };
    show(snap({ changed: [sbpTrend, hr] }));
    fireEvent.click(screen.getByRole("button", { name: "Record" }));
    fireEvent.click(screen.getByRole("tab", { name: "Trends & scores" }));
    const card = document.querySelector('[data-vital="vitals.hr"]') as HTMLElement;
    expect(card.textContent).toContain("130");
    expect(card.textContent).toContain("All from the monitor");
    expect(card.textContent).not.toContain("waiting for your tap");
    expect(card.querySelector('[aria-label="monitor"]')).toBeTruthy();       // the monitor icon, not "photo"
    expect(card.querySelectorAll('li[data-source="monitor"]').length).toBe(3);
    const etco2 = document.querySelector('[data-vital="vitals.etco2"]') as HTMLElement;
    expect(etco2.textContent).toContain("22");
  });

  it("says how much of a mixed trend came from the monitor, and nothing for a spoken-only one", () => {
    expect(monitorShare({ ...sbpTrend, from_monitor: [false, true, true] })).toBe("2 of 3 from the monitor");
    expect(monitorShare({ ...sbpTrend, from_monitor: [false, false, false] })).toBeNull();
    expect(monitorShare({ ...sbpTrend, from_monitor: undefined })).toBeNull();   // an older vehicle or fixture
  });
});
