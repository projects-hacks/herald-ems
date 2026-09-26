// The three Record tabs (Facts & sources, Trends & scores, What Herald did), reworked 2026-09-26 for a generic EMS
// call: one card per vital with BP and GCS written as a clinician writes them, a newer reading shown apart from the
// confirmed one, scores that name what they are waiting for, the county's criteria tiles, and one timeline of the call
// that includes the medic's own decisions.
import { readFileSync } from "node:fs";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CabinApp } from "@/features/cabin/CabinApp";
import { needsText } from "@/features/overview/StatTiles";
import { cardSeverity, vitalCards } from "@/pages/TrendsPage";
import { initialUi, useHerald } from "@/lib/store";
import { parseFixture } from "@/lib/ws";
import type { CriteriaScoreDetail, Snapshot } from "@/lib/types";

const base = (parseFixture(readFileSync("public/fixtures/stroke_demo.jsonl", "utf8"))[0].msg as { state: Snapshot }).state;
vi.mock("@/lib/contract", () => ({ useContract: () => ({ keys: {}, relayTiers: {}, changeRules: {} }) }));

type F = Snapshot["facts"][string];
const T0 = "2026-09-26T10:00:00.000Z", T1 = "2026-09-26T10:05:00.000Z";
function fact(over: Partial<F>): F {
  return { id: over.key ?? "f", key: "vitals.hr", label: "Heart rate", value: 88, unit: "/min", status: "confirmed",
    ts: T0, captured_by: "medic", provenance: {}, role: "medic", speaker: null,
    confidence: 1, previous_value: null, previous_ts: null, ...over } as F;
}
const facts = (...fs: F[]) => Object.fromEntries(fs.map((f) => [f.key, f]));
const snap = (over: Partial<Snapshot>): Snapshot => ({ ...base, facts: {}, changed: [], timeline: [], ...over } as Snapshot);

function openRecord(snapshot: Snapshot, tab: "Trends & scores" | "What Herald did") {
  useHerald.setState({ snapshot, source: "live", stale: false, conn: "open", ui: initialUi("") });
  render(<CabinApp />);
  fireEvent.click(screen.getByRole("button", { name: "Record" }));
  fireEvent.click(screen.getByRole("tab", { name: tab }));
}

beforeEach(() => { Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn() } }); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("vital cards", () => {
  it("writes blood pressure as systolic/diastolic on one card", () => {
    const s = snap({ facts: facts(fact({ key: "vitals.sbp", label: "Systolic BP", value: 162, unit: "mmHg" }),
      fact({ key: "vitals.dbp", label: "Diastolic BP", value: 96, unit: "mmHg" })) });
    const cards = vitalCards(s);
    expect(cards.map((c) => c.key)).toEqual(["vitals.sbp"]);
    expect(cards[0].label).toBe("Blood pressure");
    expect(cards[0].extra.map((e) => e.key)).toEqual(["vitals.dbp"]);
  });

  it("puts the GCS components on the total's card and colours it by the worse of total and motor", () => {
    const s = snap({ facts: facts(fact({ key: "vitals.gcs_total", label: "GCS total", value: 9, unit: null, severity: "abnormal" }),
      fact({ key: "vitals.gcs_eye", label: "GCS eye", value: 2, unit: null }),
      fact({ key: "vitals.gcs_verbal", label: "GCS verbal", value: 2, unit: null }),
      fact({ key: "vitals.gcs_motor", label: "GCS motor", value: 5, unit: null, severity: "critical" })) });
    const cards = vitalCards(s);
    expect(cards.map((c) => c.key)).toEqual(["vitals.gcs_total"]);
    expect(cardSeverity(cards[0])).toBe("critical");
  });

  it("orders cards the way observations are read, BP before heart rate before SpO2", () => {
    const s = snap({ facts: facts(fact({ key: "vitals.spo2", label: "SpO2", value: 95, unit: "%" }), fact({}),
      fact({ key: "vitals.sbp", label: "Systolic BP", value: 120, unit: "mmHg" })) });
    expect(vitalCards(s).map((c) => c.key)).toEqual(["vitals.sbp", "vitals.hr", "vitals.spo2"]);
  });

  it("keeps the confirmed value and shows a newer waiting reading apart, with a Confirm", () => {
    const old = fact({ id: "hr1", value: 88, ts: T0 });
    const waiting = fact({ id: "hr2", value: 132, ts: T1, status: "unconfirmed", captured_by: "device" });
    const s = snap({ facts: facts(waiting), timeline: [old, waiting] });
    const [card] = vitalCards(s);
    expect(card.latest?.id).toBe("hr1");
    expect(card.waiting?.id).toBe("hr2");
    openRecord(s, "Trends & scores");
    const el = document.querySelector('[data-vital="vitals.hr"]') as HTMLElement;
    expect(el.textContent).toContain("88");
    expect(el.textContent).toMatch(/Newer reading 132.*waiting for your tap/);
    expect(within(el).getByRole("button", { name: "Confirm" })).toBeTruthy();
  });
});

describe("scores on the Trends & scores tab", () => {

  it("names what a score is waiting for, without the mnemonic letter", () => {
    expect(needsText(["S Speech difficulties", "Air or oxygen", "SpO2 (scale 1)"])).toBe("needs speech difficulties, air or oxygen +1");
    expect(needsText(["SpO2 (scale 1)"])).toBe("needs SpO2 (scale 1)");
  });

  it("shows the score tiles once, under a Scores heading", () => {
    openRecord(snap({ facts: facts(fact({})) }), "Trends & scores");
    const scores = screen.getByRole("region", { name: "Scores" });
    expect(within(scores).getAllByRole("button", { name: /^NEWS2/ })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: /^NEWS2 .*Show details/ })).toHaveLength(1);
  });

  it("says why no value is coloured when adult ranges do not apply", () => {
    const news2 = { ...base.scores.news2, applicability: "excluded", applicability_reason: "Under 16: NEWS2 is for adults" };
    openRecord(snap({ facts: facts(fact({ value: 150 })), scores: { ...base.scores, news2 } as Snapshot["scores"] }), "Trends & scores");
    expect(screen.getByRole("note").textContent).toMatch(/Adult ranges not applied.*Under 16: NEWS2 is for adults/);
  });

  it("shows the county trauma criteria tile when its criteria are met", () => {
    const trauma: CriteriaScoreDetail = { name: "Trauma Alert (Policy 605)", county: "Santa Clara", applies: true, met: true, level: "red",
      complete: true, missing: [], source: "Santa Clara EMS Policy 605", thresholds: null,
      criteria: [{ code: "A1", label: "GCS motor < 6", state: "met" }, { code: "A2", label: "SBP < 90", state: "not_met" }] };
    openRecord(snap({ facts: facts(fact({})), scores: { ...base.scores, trauma_605: trauma } as unknown as Snapshot["scores"] }), "Trends & scores");
    const tile = screen.getByRole("button", { name: /Trauma Alert \(Policy 605\): red, 1 met/ });
    expect(tile.textContent).toContain("GCS motor < 6");
    expect(tile.textContent).toContain("met");
  });
});

describe("What Herald did", () => {

  const hr = fact({ id: "hr", value: 104 }), sbp = fact({ id: "sbp", key: "vitals.sbp", label: "Systolic BP", value: 150, unit: "mmHg" });
  const spo2 = fact({ id: "spo2", key: "vitals.spo2", label: "SpO2", value: 70, unit: "%", status: "rejected" });
  const audit: Snapshot["audit"] = [
    { at: "2026-09-26T10:01:00.100Z", action: "fact_status_changed", actor: "medic", fact_id: "hr", key: "vitals.hr", from: "unconfirmed", to: "confirmed" },
    { at: "2026-09-26T10:01:00.400Z", action: "fact_status_changed", actor: "medic", fact_id: "sbp", key: "vitals.sbp", from: "unconfirmed", to: "confirmed" },
    { at: "2026-09-26T10:02:00.000Z", action: "fact_status_changed", actor: "medic", fact_id: "spo2", key: "vitals.spo2", from: "unconfirmed", to: "rejected" },
    { at: "2026-09-26T10:03:00.000Z", action: "fact_status_changed", actor: "system", fact_id: "hr", key: "vitals.hr", from: "confirmed", to: "unconfirmed" },
  ];

  it("lists the medic's decisions, one line per tap, newest first", () => {
    openRecord(snap({ facts: facts(hr, sbp, spo2), audit, transcripts: [] }), "What Herald did");
    const rows = Array.from(document.querySelectorAll('li[data-kind="you"]')).map((li) => li.textContent);
    expect(rows).toHaveLength(2);                           // the bulk confirm is one line; the system change is not the medic's
    expect(rows[0]).toMatch(/You rejected SpO2 70/);
    expect(rows[1]).toMatch(/You confirmed 2 facts/);
    expect(rows[1]).toMatch(/Heart rate 104.*Systolic BP 150/);
  });

  it("filters the timeline, and says so when a filter has nothing", () => {
    openRecord(snap({ facts: facts(hr, sbp, spo2), audit, transcripts: [] }), "What Herald did");
    const show = screen.getByRole("group", { name: "Show" });
    fireEvent.click(within(show).getByRole("button", { name: /Your actions/ }));
    expect(within(show).getByRole("button", { name: /Your actions/ }).getAttribute("aria-pressed")).toBe("true");
    expect(document.querySelectorAll("li[data-kind]").length).toBe(2);
    expect(Array.from(document.querySelectorAll("li[data-kind]")).every((li) => li.getAttribute("data-kind") === "you")).toBe(true);
    fireEvent.click(within(show).getByRole("button", { name: /Heard & seen/ }));
    expect(screen.getByText("Nothing of this kind yet")).toBeTruthy();
  });

  it("draws no rule above the first row of the timeline", () => {
    openRecord(snap({ facts: facts(hr, sbp, spo2), audit, transcripts: [] }), "What Herald did");
    const rules = Array.from(document.querySelectorAll('li[data-kind="you"] > div')).map((d) => d.classList.contains("border-t"));
    expect(rules).toEqual([false, true]);
  });
});
