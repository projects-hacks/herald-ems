import { readFileSync } from "node:fs";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { TraceEntry } from "@/features/trace/trace";
import { TranscriptPage } from "@/pages/TranscriptPage";
import { useHerald } from "@/lib/store";
import type { Snapshot, TranscriptEntry } from "@/lib/types";

const original: Snapshot = JSON.parse(readFileSync("src/test/fixtures/live_every_call.json", "utf8"));
let snapshot: Snapshot;
let entry: TranscriptEntry;
beforeEach(() => {
  snapshot = structuredClone(original);
  entry = { ...snapshot.transcripts[0], trigger: "region_changed", photo_id: "test-photo", audio_id: "test-audio" };
  entry.trace.model = { ...entry.trace.model, status: "done", ms: 1234 };
  snapshot.transcripts = [entry];
  useHerald.setState({ snapshot, source: "live", conn: "open", stale: false,
    ui: { ...useHerald.getState().ui, mode: "medic", page: "overview" } });
});
afterEach(cleanup);

it("discloses technical processing only on expansion while retaining source evidence", () => {
  render(<TranscriptPage />);
  const details = screen.getByText("Processing details").closest("details")!;
  expect(details.open).toBe(false);
  expect(screen.getByText("Capture trigger · region_changed").closest("details")).toBe(details);
  expect(screen.getByText("1234 ms").closest("details")).toBe(details);
  expect(screen.getByAltText("Stored capture evidence; open full image").closest("details")).toBeNull();
  expect(screen.getByLabelText("Play source audio").closest("details")).toBeNull();
  expect(screen.getByText(`“${entry.text}”`).closest("details")).toBeNull();
});

it.each([
  ["running", "Processing captured information…", "status"],
  ["error", "Could not extract facts — review this capture", "alert"],
  ["unavailable", "Extraction unavailable — captured words retained, no new facts extracted", "alert"],
] as const)("keeps %s state outside collapsed processing details", (status, message, role) => {
  entry.trace.model.status = status;
  render(<TraceEntry t={entry} concise />);
  const state = screen.getByRole(role);
  expect(state.textContent).toContain(message);
  expect(state.closest("details")).toBeNull();
});

it("routes a mismatch to the caller's review panel without confirming a fact", () => {
  const dose = snapshot.events!["meds.given"][0];
  dose.status = "unconfirmed";
  dose.verify = { status: "mismatch", label_drug: "ondansetron", photo_id: null, resolution: null };
  entry.fact_ids = [dose.id];
  const review = vi.fn();
  render(<TranscriptPage onReview={review} />);
  fireEvent.click(screen.getByRole("button", { name: "Review mismatch" }));
  expect(review).toHaveBeenCalledOnce();
  expect(screen.queryByRole("button", { name: "Confirm" })).toBeNull();
  expect(dose.status).toBe("unconfirmed");
});

it("preserves expanded processing presentation by default in the detailed trace", () => {
  render(<TraceEntry t={entry} />);
  expect(screen.queryByText("Processing details")).toBeNull();
  expect(screen.getByText("1234 ms").closest("details")).toBeNull();
});
