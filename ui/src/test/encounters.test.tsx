import { readFileSync } from "node:fs";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { EncounterControls, EncounterHistory } from "@/features/cabin/EncounterControls";
import { PatientRoster } from "@/components/PatientRoster";
import { RestoredCallBanner } from "@/components/GlobalStates";
import { CabinApp } from "@/features/cabin/CabinApp";
import { api } from "@/lib/api";
import { useHerald, initialUi } from "@/lib/store";
import { parseFixture } from "@/lib/ws";
import type { Snapshot } from "@/lib/types";
const base = (parseFixture(readFileSync("public/fixtures/stroke_demo.jsonl", "utf8"))[0].msg as { state: Snapshot }).state;
vi.mock("@/lib/contract", () => ({ useContract: () => ({ keys: {}, relayTiers: {}, changeRules: {} }) }));
beforeEach(() => {
  useHerald.setState({ snapshot: { ...base, restored: false }, source: "live", conn: "open", stale: false, ui: initialUi(""), pending: {} });
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn() } });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("always exposes Patients and separates same-scene add from finishing", async () => {
  render(<CabinApp />);
  fireEvent.click(screen.getByRole("button", { name: "Patients" }));
  expect(screen.getByRole("button", { name: "Add patient at this scene" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Finish encounter and start next…" })).toBeTruthy();
  expect(screen.getByText(/Name and date of birth are optional/)).toBeTruthy();
});

it("adds an unidentified patient without requiring a label or finishing the current one", async () => {
  const add = vi.spyOn(api, "addPatient").mockResolvedValue(true);
  const finish = vi.spyOn(api, "encounterAction");
  render(<PatientRoster expanded />);
  fireEvent.click(screen.getByRole("button", { name: "Add patient at this scene" }));
  await waitFor(() => expect(add).toHaveBeenCalledWith(`Patient ${(base.patients?.length ?? 0) + 1}`));
  expect(finish).not.toHaveBeenCalled();
});

it.each(["restored", "finished"])("does not start either device for a %s encounter", (kind) => {
  useHerald.setState({ snapshot: { ...base, restored: kind === "restored", incident: { ...base.incident, ended_at: kind === "finished" ? new Date().toISOString() : null } } });
  render(<CabinApp />);
  expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
  if (kind === "restored") expect(screen.getByRole("button", { name: "Continue with this patient" })).toBeTruthy();
  else expect(screen.getByRole("heading", { name: "Encounter finished" })).toBeTruthy();
});

it("records transfer only on the explicit transfer button", async () => {
  const mark = vi.spyOn(api, "encounterAction").mockResolvedValue(true);
  render(<EncounterControls />);
  expect(mark).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Record transfer of care now" }));
  await waitFor(() => expect(mark).toHaveBeenCalledWith("transfer"));
});

it("read-only history does not activate a patient or change capture", async () => {
  const active = base.incident.id;
  const activate = vi.spyOn(api, "activatePatient");
  useHerald.setState({ snapshot: { ...base, encounter_history: [{ id: "old", label: "Patient 1", summary: "Previous call", triage: null, readiness_done: 0, readiness_total: 0, started: base.incident.started, authorized: true, destination: "First ED", delivery_pending: true }], history_persisted: true } });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ incident: { id: "old" }, handoff: { text: "Prior confirmed record" } }) }));
  render(<EncounterHistory />);
  fireEvent.click(screen.getByRole("button", { name: /Patient 1 · old/ }));
  await screen.findByText("Prior confirmed record");
  expect(activate).not.toHaveBeenCalled();
  expect(useHerald.getState().snapshot?.incident.id).toBe(active);
});

it("resuming requires the medic's tap", async () => {
  const resume = vi.spyOn(api, "resumeEncounter").mockResolvedValue(true);
  useHerald.setState({ snapshot: { ...base, restored: true } });
  render(<RestoredCallBanner />);
  expect(resume).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Continue with this patient" }));
  await waitFor(() => expect(resume).toHaveBeenCalledOnce());
});
