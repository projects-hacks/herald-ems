// The handoff layout: the report as rows (no time in every value), the latest vitals as tiles, and who told us what,
// from the server's `informants` or, for an older server or a recording, derived from the lines' sources.
import { readFileSync } from "node:fs";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HandoffPage } from "@/pages/HandoffPage";
import { PatientPage } from "@/pages/PatientPage";
import { deriveInformants, reportInformants } from "@/features/handoff/informants";
import { splitLine } from "@/features/handoff/HandoffReport";
import { leftoverSummary } from "@/features/handoff/BeforeHandover";
import { initialUi, useHerald } from "@/lib/store";
import { parseFixture } from "@/lib/ws";
import type { HandoffReportData, HandoffSection, HandoffSource, Snapshot } from "@/lib/types";

const keys = JSON.parse(readFileSync("public/contract/keys.json", "utf8"));
const label = (key: string) => keys[key]?.label ?? key;
vi.mock("@/lib/contract", () => ({
  useContract: () => ({ keys, relayTiers: {}, changeRules: {} }),
  label: (_c: unknown, key: string) => keys[key]?.label ?? key,
}));
const recorded = (parseFixture(readFileSync("public/fixtures/stroke_demo.jsonl", "utf8")).at(-1)!.msg as { state: Snapshot }).state;

const src = (key: string, role: string, speaker: string | null = null, ts = "2026-09-26T14:02:00Z"): HandoffSource =>
  ({ fact_id: `f_${key}_${role}`, key, role, speaker, captured_by: role === "device" ? "camera" : "medic", ts });

// the shape GET /api/handoff sends (2026-09-26): each line with its keys and the sources behind it
const sections: HandoffSection[] = [
  { id: "situation", label: "S: Situation", lines: [
    { kind: "fact", status: "confirmed", text: "68-year-old female", keys: ["patient.age", "patient.sex"], sources: [src("patient.age", "medic"), src("patient.sex", "medic")] },
    { kind: "fact", status: "confirmed", text: "Chief complaint: suspected stroke", keys: ["complaint.chief"], sources: [src("complaint.chief", "unknown", "Speaker not identified")] },
  ] },
  { id: "background", label: "B: Background", lines: [
    { kind: "fact", status: "confirmed", text: "Allergies: none reported", keys: ["allergies"], sources: [src("allergies", "family", "husband")] },
    { kind: "fact", status: "confirmed", text: "Medications: warfarin", keys: ["meds.list"], sources: [src("meds.list", "family", "husband")] },
    { kind: "missing", status: "missing", text: "Anticoagulant: not yet known", keys: ["meds.anticoagulant"], sources: [] },
  ] },
  { id: "assessment", label: "A: Assessment", lines: [
    { kind: "fact", status: "confirmed", text: "HR 104 /min", keys: ["vitals.hr"], sources: [src("vitals.hr", "device")] },
    { kind: "fact", status: "confirmed", text: "SpO2 94 %", keys: ["vitals.spo2"], sources: [src("vitals.spo2", "device")] },
    { kind: "fact", status: "confirmed", text: "RR 22 /min", keys: ["vitals.rr"], sources: [src("vitals.rr", "patient")] },
    // an unconfirmed value never reaches a line, but a stray source on a missing line must not name anyone either
    { kind: "missing", status: "missing", text: "Glucose: not yet known", keys: ["vitals.glucose"], sources: [src("vitals.glucose", "bystander", "neighbour")] },
  ] },
];

describe("who told us what", () => {
  it("groups the confirmed lines' sources the way the server does: others, patient, monitor, medic, not identified", () => {
    const rows = deriveInformants(sections, label);
    expect(rows.map((r) => r.who)).toEqual(["husband", "patient", "patient monitor", "medic", "speaker not identified"]);
    expect(rows[0]).toMatchObject({ role: "family", keys: ["allergies", "meds.list"], items: [label("allergies"), label("meds.list")] });
    expect(rows[2].items).toEqual([label("vitals.hr"), label("vitals.spo2")]);
    expect(rows.flatMap((r) => r.who)).not.toContain("neighbour");
  });
  it("names a relative or bystander by who they are, and falls back to the role without a speaker", () => {
    const rows = deriveInformants([{ id: "x", label: "X", lines: [{ status: "confirmed", text: "t", sources: [
      src("allergies", "family", "daughter"), src("meds.list", "family", null), src("allergies", "bystander", "neighbour"), src("vitals.hr", "family", "daughter")] }] }], label);
    expect(rows.map((r) => [r.who, r.keys])).toEqual([["daughter", ["allergies", "vitals.hr"]], ["family", ["meds.list"]], ["neighbour", ["allergies"]]]);
  });
  it("uses the server's list when it sends one, and derives it for a report that predates the field", () => {
    const report = { sections, informants: [{ who: "wife", role: "family", keys: ["allergies"], items: ["Allergies"] }] } as HandoffReportData;
    expect(reportInformants(report, label).map((r) => r.who)).toEqual(["wife"]);
    expect(reportInformants({ ...report, informants: undefined }, label)[0].who).toBe("husband");
    expect(deriveInformants([{ id: "x", label: "X", lines: [{ text: "old line", status: "confirmed" }] }], label)).toEqual([]);
  });
});

describe("the handoff layout", () => {
  let report: HandoffReportData;
  beforeEach(() => {
    report = { incident: { id: recorded.incident.id }, as_of: "2026-09-26T14:05:00Z", text: "", sections,
      format: { id: "medical", label: "SBAR (medical)", title: "Medical handover (SBAR)" }, formats: [{ id: "mist", label: "MIST (trauma)" }, { id: "medical", label: "SBAR (medical)" }],
      not_yet_known: [], not_yet_confirmed: [], not_obtained: [],
      informants: [{ who: "husband", role: "family", keys: ["allergies", "meds.list"], items: ["Allergies", "Medications"] },
        { who: "patient monitor", role: "device", keys: ["vitals.hr"], items: ["Heart rate", "SpO2"] }] };
    vi.stubGlobal("fetch", vi.fn(async (url: string) => (url.startsWith("/api/handoff") ? { ok: true, json: async () => report } : { ok: false, json: async () => ({}) })));
    useHerald.setState({ snapshot: structuredClone(recorded), source: "live", conn: "open", stale: false, pending: {}, ui: initialUi("") });
  });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("shows each line as its own row, with one 'as of' time and each fact's time only on hover", async () => {
    render(<HandoffPage />);
    const r = await waitFor(() => {
      const region = screen.getByRole("region", { name: "Handoff report" });
      within(region).getByText("suspected stroke");
      return region;
    });
    const row = within(r).getByText("suspected stroke").closest("li")!;
    expect(row.getAttribute("data-status")).toBe("confirmed");
    expect(within(row).getByText("Chief complaint:")).toBeTruthy();
    expect(row.textContent).not.toMatch(/\(\d\d:\d\d\)/);
    expect(row.getAttribute("title")).toMatch(/^Speaker not identified \d\d:\d\d$/);
    // vitals the tiles beside the report already show are not repeated as rows
    expect(within(r).getAllByRole("listitem").filter((li) => li.getAttribute("data-status") === "confirmed")).toHaveLength(4);
    expect(within(r).queryAllByRole("listitem").some((li) => /^(HR|BP|SpO2|Heart rate|Blood pressure)\b/.test(li.textContent ?? ""))).toBe(false);
    expect(within(r).getByText(/^As of \d\d:\d\d$/)).toBeTruthy();
    // missing items stay in their section, quiet
    const missing = within(r).getAllByText("not yet known", { selector: ".report-line-value" }).map((el) => el.closest("li")!);
    expect(missing.map((li) => [li.textContent, li.getAttribute("data-status")])).toEqual([
      ["Anticoagulant: not yet known", "missing"], ["Glucose: not yet known", "missing"]]);
    expect(splitLine("HR 104 /min")).toEqual([null, "HR 104 /min"]);
    expect(splitLine("Sepsis alert: pre-notification criteria met")).toEqual(["Sepsis alert", "pre-notification criteria met"]);
  });

  it("renders the Who told us card from the server's informants", async () => {
    render(<HandoffPage />);
    const card = await screen.findByRole("region", { name: "Who told us what" });
    const rows = within(card).getAllByRole("listitem");
    expect(rows.map((li) => li.textContent)).toEqual(["HusbandAllergies, Medications", "Patient monitorHeart rate, SpO2"]);
  });

  it("derives the card from the recorded demo, which predates the field", () => {
    useHerald.setState({ source: "fixture" });
    render(<HandoffPage />);
    const card = screen.getByRole("region", { name: "Who told us what" });
    const [husband, medic] = within(card).getAllByRole("listitem");
    expect(husband.textContent).toBe(`Husband${label("patient.name")}, ${label("stroke.lkw")}`);
    expect(medic.textContent).toContain("Medic");
    // the recording's report carries no clock time inside a value either
    expect(screen.getByRole("region", { name: "Handoff report" }).textContent).not.toMatch(/\(\d\d:\d\d\)/);
    // the unconfirmed allergy (the daughter's) is never attributed
    expect(card.textContent).not.toContain("Daughter");
  });

  it("shows the latest confirmed vitals as tiles, blood pressure paired", async () => {
    render(<HandoffPage />);
    const tiles = await screen.findByRole("region", { name: "Latest vitals" });
    const bp = within(tiles).getByLabelText(/^Blood pressure: 182\/104 mmHg/);
    expect(bp.textContent).toContain("182/104");
    expect(bp.getAttribute("title")).toMatch(/^Recorded \d\d:\d\d$/);
    expect(within(tiles).getByLabelText(/^Heart rate: 104/)).toBeTruthy();
  });

  it("puts who, why, where and the ED status in the header card", () => {
    // the recording has no chief complaint fact (the extractor did not state one), so the test gives the card one
    const s = structuredClone(recorded);
    s.facts["complaint.chief"] = { ...s.facts["patient.age"], id: "f_cc", key: "complaint.chief", label: "Chief complaint", value: "suspected stroke" };
    useHerald.setState({ snapshot: s, source: "fixture" });
    render(<HandoffPage />);
    const header = document.querySelector<HTMLElement>(".handoff-headline")!;
    expect(within(header).getByRole("heading", { level: 1 }).textContent).toBe("Margaret Wilson · 68 y · F");   // the confirmed name the husband gave
    expect(within(header).getByText("suspected stroke")).toBeTruthy();
    expect(within(header).getByText("Regional (heard “Regional”)")).toBeTruthy();   // the destination says how it was chosen
    expect(within(header).getByText("ETA")).toBeTruthy();
  });

  it("counts what is left by kind in one line", () => {
    expect(leftoverSummary({ confirm: 2, choose: 1, missing: 0, notObtained: 0 })).toBe("2 need a tap, 1 conflict");
    expect(leftoverSummary({ confirm: 1, choose: 0, missing: 3, notObtained: 1 })).toBe("1 needs a tap, 3 not recorded, 1 unable to obtain");
  });
});

describe("the record's evidence line", () => {
  afterEach(() => cleanup());
  it("says when the speaker was read from the words", () => {
    const s = structuredClone(recorded);
    s.facts["stroke.lkw"].provenance = { ...s.facts["stroke.lkw"].provenance, heard_as: "husband" };
    useHerald.setState({ snapshot: s, source: "fixture", ui: initialUi("") });
    render(<PatientPage />);
    expect(screen.getAllByText(/husband \(from the words\)/)).toHaveLength(1);
  });
});
