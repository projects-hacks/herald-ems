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
    // The same abnormal-stable vital shows both on the Trends-tab card and on the live movement panel; both are
    // correct. Assert a Trends-tab card carries "critical" without a "big change" badge.
    const cards = screen.getAllByLabelText("SpO2, critical");
    expect(cards.length).toBeGreaterThan(0);
    expect(cards.some((c) => c.textContent?.includes("critical") && !c.textContent?.includes("big change"))).toBe(true);
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

  it("colours an out-of-range value on the live 'How the patient is moving' panel, even when it did not move", () => {
    // The panel a medic watches during the call, not the Trends tab. A steady-but-critical vital used to be silent
    // here. It is surfaced from confirmed facts when there is no trend row (single reading).
    useHerald.setState({
      snapshot: { ...base, facts: { "vitals.spo2": fact({ severity: "critical" }) }, changed: [] },
      source: "live", stale: false, conn: "open", ui: initialUi(""),
    });
    render(<CabinApp />);
    const movement = screen.getByRole("region", { name: "How the patient is moving" });
    expect(movement.textContent).toContain("critical");
    expect(movement.textContent).not.toContain("big change");
  });

  it("shows severity on a lone value the medic is asked to confirm in 'Needs you'", () => {
    // A single spoken unconfirmed vital renders as a TapRow in the attention queue; its severity must show at the
    // point of the confirm decision.
    const unconfirmed = fact({ id: "u1", status: "unconfirmed", captured_by: "medic", severity: "critical",
      provenance: { audio_id: "a1", text: "sats are 84", frame_id: null } as unknown as Snapshot["facts"][string]["provenance"] });
    useHerald.setState({
      snapshot: { ...base, facts: { "vitals.spo2": unconfirmed } },
      source: "live", stale: false, conn: "open", ui: initialUi(""),
    });
    render(<CabinApp />);
    const needs = screen.getByRole("region", { name: /Needs you/ });
    expect(needs.textContent).toContain("critical");
  });
});


describe("SpO2 target switch", () => {
  beforeEach(() => { Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn() } }); });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });
  const withSpo2 = (extra: Record<string, Snapshot["facts"][string]> = {}, applicability = "applicable") =>
    useHerald.setState({ snapshot: { ...base, facts: { "vitals.spo2": fact({ value: 90 }), ...extra },
      scores: { ...base.scores, news2: { ...base.scores.news2, applicability } } } as Snapshot,
      source: "live", stale: false, conn: "open", ui: initialUi("") });

  it("offers a one-tap switch that posts Scale 2 when on Scale 1", () => {
    withSpo2();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 200 }));
    render(<CabinApp />);
    const sw = screen.getByRole("switch", { name: /COPD SpO2 target/ });
    expect(sw.getAttribute("aria-checked")).toBe("false");
    expect(screen.getByRole("group", { name: "Patient" }).textContent).toContain("94–98%");
    fireEvent.click(sw);
    const call = fetchMock.mock.calls.find(([u]) => String(u).includes("/api/patient/spo2-scale"));
    expect(call).toBeTruthy();
    expect(JSON.parse(String((call![1] as RequestInit).body))).toEqual({ scale: 2 });
  });

  it("shows the COPD target as on once Scale 2 is confirmed", () => {
    withSpo2({ "patient.spo2_scale": fact({ id: "s2", key: "patient.spo2_scale", label: "SpO2 target scale (NEWS2)", value: 2, unit: null }) });
    render(<CabinApp />);
    expect(screen.getByRole("switch", { name: /COPD SpO2 target/ }).getAttribute("aria-checked")).toBe("true");
    expect(screen.getByRole("group", { name: "Patient" }).textContent).toContain("88–92%");
  });

  it("is not offered where adult ranges do not apply", () => {
    withSpo2({}, "excluded");
    render(<CabinApp />);
    expect(screen.queryByRole("switch", { name: /COPD SpO2 target/ })).toBeNull();
  });
});
