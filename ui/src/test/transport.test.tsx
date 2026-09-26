import { readFileSync } from "node:fs";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { DestinationDialog, routingNote } from "@/features/transport/DestinationDialog";
import { SituationBar } from "@/features/copilot/Copilot";
import { EndIncidentDialog } from "@/components/GlobalStates";
import { api } from "@/lib/api";
import { useHerald, initialUi } from "@/lib/store";
import { parseFixture } from "@/lib/ws";
import type { Snapshot, TransportView } from "@/lib/types";

const base = (parseFixture(readFileSync("public/fixtures/stroke_demo.jsonl", "utf8"))[0].msg as { state: Snapshot }).state;
const dispositions = JSON.parse(readFileSync("public/contract/dispositions.json", "utf8"));
vi.mock("@/lib/contract", () => ({ useContract: () => ({ keys: {}, relayTiers: {}, changeRules: {}, dispositions }),
  label: (_c: unknown, k: string) => k }));

const transport = (patch: Partial<TransportView> = {}): TransportView => ({
  routing: true, router_error: null, position: { at: "2026-09-26T01:00:00Z", accuracy_m: 8, fresh: true },
  options: [
    { id: "RSJ", name: "Regional Medical Center of San Jose", designations: ["Comprehensive Stroke Center", "Primary Stroke Center"], point: "campus", minutes: 9, km: 6.1 },
    { id: "VMC", name: "Santa Clara Valley Medical Center", designations: ["Primary Stroke Center"], point: "campus", minutes: 14, km: 9.8 },
  ],
  destination: null, eta: null, ...patch,
});
const show = (t: TransportView, extra: Partial<Snapshot> = {}) => useHerald.setState({
  snapshot: { ...base, transport: t, ...extra }, source: "live", conn: "open", stale: false, ui: { ...initialUi(""), destinationOpen: true }, pending: {} });
beforeEach(() => show(transport()));
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("lists the county's hospitals nearest first with drive time and marks stroke designations on a stroke call", () => {
  render(<DestinationDialog />);
  const rows = screen.getAllByRole("button", { pressed: false }).filter((b) => b.className === "destination-row");
  expect(rows.map((r) => r.querySelector(".destination-name")!.textContent)).toEqual(["Regional Medical Center of San Jose", "Santa Clara Valley Medical Center"]);
  expect(screen.getByText("9 min · 6.1 km")).toBeTruthy();
  expect(document.querySelector('.destination-tag[data-relevant]')!.textContent).toMatch(/Stroke Center/);
  expect(screen.getByText(/Diversion and bed status are not available/)).toBeTruthy();   // Herald does not know it
});

it("offers what was heard as a suggestion; the medic's tap sets the destination", async () => {
  const set = vi.spyOn(api, "setDestination").mockResolvedValue(true);
  show(transport({ destination: { fact_id: "f1", value: "Regional", status: "unconfirmed", id: null, suggested: "RSJ", matching: false } }));
  render(<DestinationDialog />);
  expect(screen.getByText("Heard “Regional”")).toBeTruthy();
  fireEvent.click(document.querySelector(".destination-heard button")!);
  await waitFor(() => expect(set).toHaveBeenCalledWith("RSJ"));
  expect(useHerald.getState().ui.destinationOpen).toBe(false);
});

it("says why there are no drive times instead of showing guesses", () => {
  expect(routingNote(transport({ routing: false }))).toMatch(/not set up/);
  expect(routingNote(transport({ position: null }))).toMatch(/shares its location/);
  expect(routingNote(transport({ position: { at: "x", accuracy_m: 5, fresh: false } }))).toMatch(/out of date/);
  expect(routingNote(transport({ router_error: "ConnectError" }))).toMatch(/unavailable/);
  expect(routingNote(transport())).toBeNull();
});

it("the situation bar names the destination and whether the ETA is the road route or the crew's estimate", () => {
  const until = new Date(Date.now() + 9 * 60000).toISOString();
  show(transport({ destination: { fact_id: "f", value: "Regional Medical Center of San Jose", status: "confirmed", id: "RSJ", suggested: null, matching: false } }),
    { clocks: [...base.clocks.filter((c) => c.id !== "eta"), { id: "eta", label: "ETA", seconds: 540, until, source: "route" }] });
  render(<SituationBar />);
  expect(screen.getByText("road route")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Destination Regional Medical Center of San Jose, 9 minutes by road. Change" })).toBeTruthy();
});

it("finishing needs an outcome, and a transported patient cannot be finished as not transported", async () => {
  const finish = vi.spyOn(api, "finishEncounter").mockResolvedValue(true);
  useHerald.getState().setUi({ confirmEndIncident: true });
  render(<EndIncidentDialog />);
  const go = screen.getByRole("button", { name: "Finish encounter" }) as HTMLButtonElement;
  expect(go.disabled).toBe(true);
  fireEvent.click(screen.getByLabelText(/Evaluated, not transported/));
  fireEvent.click(go);
  await waitFor(() => expect(finish).toHaveBeenCalledWith("not_transported"));
  cleanup();
  show(transport(), { incident: { ...base.incident, arrived_at: "2026-09-26T01:20:00Z" } });
  useHerald.getState().setUi({ confirmEndIncident: true });
  render(<EndIncidentDialog />);
  expect((screen.getByLabelText(/Patient refused transport/) as HTMLInputElement).disabled).toBe(true);
  expect((screen.getByLabelText(/Transported by this unit/) as HTMLInputElement).disabled).toBe(false);
});
