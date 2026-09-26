import { readFileSync } from "node:fs";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { initialUi, useHerald } from "@/lib/store";
import { traumaCriteriaRows } from "@/lib/selectors";
import type { Alert, Snapshot } from "@/lib/types";
import { AttentionQueue } from "@/features/attention/AttentionQueue";

// Speech recall on trauma.criteria measures ~0.2 (docs/MODEL_PLAN.md bake-off): most Policy 605 injury-pattern
// criteria a medic actually observed are never heard. These tests exercise the tappable checklist that stands
// in for that gap -- every county criterion listed, a heard-but-unconfirmed one needing one tap, an unheard one
// needing a tap to add and a tap to confirm -- using the real bundled contract, not a hand-typed stand-in.
const base: Snapshot = JSON.parse(readFileSync("src/test/fixtures/live_every_call.json", "utf8"));
const keys = JSON.parse(readFileSync("public/contract/keys.json", "utf8"));
const scores = JSON.parse(readFileSync("public/contract/scores.json", "utf8"));
const contract = { keys, relayTiers: {}, changeRules: {}, checklists: { trauma: { label: "Trauma" } }, scores };
vi.mock("@/lib/contract", () => ({ useContract: () => contract, label: (_c: unknown, key: string) => keys[key]?.label ?? key }));

let snapshot: Snapshot;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  snapshot = structuredClone(base);   // already carries a real trauma_605 score and one unconfirmed trauma.criteria fact
  const trauma: Alert = { type: "trauma_alert_criteria", label: "Trauma Alert criteria met", level: "yellow", score: "trauma_605", criteria: [] };
  snapshot.alerts = [trauma];
  fetchMock = vi.fn(async () => ({ ok: true, json: async () => snapshot }));
  useHerald.setState({ snapshot, source: "live", conn: "open", stale: false, pending: {}, health: null, ui: initialUi("") });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("shows every county criterion, not only the ones speech caught, with an honest confirmed-count label", () => {
  render(<AttentionQueue />);
  expect(screen.getByText(/Based on 0 confirmed criteria — not a complete screen/)).toBeTruthy();
  // B (skull deformity) was never mentioned: still listed, tappable.
  expect(screen.getByText(/B\. Skull deformity/)).toBeTruthy();
  // X.6 was heard by speech but is unconfirmed in the fixture: shown distinctly from an unmarked criterion.
  expect(screen.getByText(/heard, not confirmed/)).toBeTruthy();
});

it("marking a criterion speech never heard posts the exact county value through the existing facts endpoint", async () => {
  render(<AttentionQueue />);
  const row = screen.getByText(/B\. Skull deformity/).closest("li")!;
  fireEvent.click(within(row).getByRole("button", { name: "Mark" }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/facts", expect.objectContaining({
    method: "POST", body: JSON.stringify([{ key: "trauma.criteria", value: ["skull deformity"], unit: null }]),
  })));
});

it("confirming a heard-but-unconfirmed criterion uses the same confirm endpoint as any other fact", async () => {
  render(<AttentionQueue />);
  const row = screen.getByText(/heard, not confirmed/).closest("li")!;
  fireEvent.click(within(row).getByRole("button", { name: "Confirm" }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/facts/f_6581b849ec/confirm", expect.objectContaining({ method: "POST" })));
});

it("leaves vitals/medication criteria read-only: no tap target where the backend cannot record one from a tap", () => {
  render(<AttentionQueue />);
  // J (GCS motor) is decided from vitals, never from a checklist tap.
  const row = screen.getByText(/J\. Unable to follow commands/).closest("li")!;
  expect(within(row).queryByRole("button")).toBeNull();
  expect(within(row).getByText(/from vitals\/meds, not here/)).toBeTruthy();
});

it("falls back to the alert's own met-criteria list when the score's contract rows are unavailable", () => {
  // traumaCriteriaRows returns nothing when contractRows is undefined (e.g. an older bundled contract);
  // TraumaCriteriaChecklist renders the alert's own already-met list instead of an empty panel.
  expect(traumaCriteriaRows(snapshot, undefined, "trauma_605")).toEqual([]);
});

it("leads with what is met or heard and folds the rest of the county list, with no form to submit", () => {
  render(<AttentionQueue />);
  const heard = screen.getByRole("list", { name: "Criteria heard" });
  expect(within(heard).getByText(/heard, not confirmed/)).toBeTruthy();
  const folded = screen.getByText(/Add a criterion speech missed/).closest("details")!;
  expect(folded.open).toBe(false);
  expect(within(folded).getByText(/B\. Skull deformity/)).toBeTruthy();
  expect(within(folded).getByText(/There is nothing to submit/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: /submit/i })).toBeNull();
});
