import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { DestinationDialog, routingNote } from "@/features/transport/DestinationDialog";
import { EdCard, SituationBar } from "@/features/copilot/Copilot";
import { EndIncidentDialog } from "@/components/GlobalStates";
import { EVERY_MS, useVehicleLocation } from "@/features/transport/useVehicleLocation";
import { api } from "@/lib/api";
import { useHerald, initialUi } from "@/lib/store";
import { parseFixture } from "@/lib/ws";
import type { Snapshot, TransportSuggestion, TransportView } from "@/lib/types";

const base = (parseFixture(readFileSync("public/fixtures/stroke_demo.jsonl", "utf8"))[0].msg as { state: Snapshot }).state;
const dispositions = JSON.parse(readFileSync("public/contract/dispositions.json", "utf8"));
vi.mock("@/lib/contract", () => ({ useContract: () => ({ keys: {}, relayTiers: {}, changeRules: {}, dispositions }),
  label: (_c: unknown, k: string) => k }));

const RSJ = "Regional Medical Center of San Jose";
const transport = (patch: Partial<TransportView> = {}): TransportView => ({
  routing: true, router_error: null, position: { at: "2026-09-26T01:00:00Z", accuracy_m: 8, fresh: true },
  options: [
    { id: "RSJ", name: RSJ, designations: ["Comprehensive Stroke Center", "Primary Stroke Center"], point: "campus", minutes: 9, km: 6.1 },
    { id: "VMC", name: "Santa Clara Valley Medical Center", designations: ["Primary Stroke Center"], point: "campus", minutes: 14, km: 9.8 },
  ],
  destination: null, heard: null, suggestion: null, eta: null, ...patch,
});
const suggestion = (patch: Partial<TransportSuggestion> = {}): TransportSuggestion => ({
  id: "RSJ", name: RSJ, designations: ["Comprehensive Stroke Center"], minutes: 9, km: 6.1, nearest_known: true,
  basis: "policy", rule: "stroke_comprehensive", situation: "Stroke Alert, G.F.A.S.T. 4 of 4", service: "Comprehensive Stroke Center",
  cite: "602 §VI.E.1.a; 700-A13 §3.2", quote: "The closest Comprehensive Stroke Center …", note: null, ...patch,
});
const heardRsj = { fact_id: "f", value: RSJ, id: "RSJ", how: "heard" as const, said: "Regional", at: "2026-09-26T01:00:00Z" };
const show = (t: TransportView, extra: Partial<Snapshot> = {}) => useHerald.setState({
  snapshot: { ...base, transport: t, ...extra }, source: "live", conn: "open", stale: false, ui: { ...initialUi("") }, pending: {} });
beforeEach(() => show(transport()));
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers(); vi.unstubAllGlobals(); });

it("Herald suggests one hospital from the county rule with a single Accept; the list is not on the screen", async () => {
  const set = vi.spyOn(api, "setDestination").mockResolvedValue(true);
  show(transport({ suggestion: suggestion() }));
  render(<SituationBar />);
  expect(screen.getByText(/, Comprehensive Stroke Center, 9 min by road/).textContent).toBe(`Herald suggests ${RSJ}, Comprehensive Stroke Center, 9 min by road`);
  expect(screen.getByText(/Stroke Alert, G\.F\.A\.S\.T\. 4 of 4 · 602 §VI\.E\.1\.a/)).toBeTruthy();
  expect(screen.getByText("Accept, or say the hospital")).toBeTruthy();
  expect(document.querySelector(".destination-row")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Accept" }));
  await waitFor(() => expect(set).toHaveBeenCalledWith("RSJ", "suggestion"));
});

it("without a vehicle position the suggestion says the nearest is not known", () => {
  show(transport({ position: null, suggestion: suggestion({ id: "ECH", name: "El Camino Hospital of Mountain View", minutes: null, km: null, nearest_known: false }) }));
  render(<SituationBar />);
  expect(screen.getByText(/Comprehensive Stroke Center · no location, nearest not known/)).toBeTruthy();
});

it("words that name no single county hospital are shown as heard, never as the destination", () => {
  show(transport({ heard: { fact_id: "h", value: "Kaiser", role: "medic", state: "unmatched", id: null }, suggestion: suggestion() }));
  render(<SituationBar />);
  expect(screen.getByRole("status").textContent).toBe("Heard“Kaiser”, not matched to a county hospital");
  expect(screen.queryByText(/^To$/)).toBeNull();
  expect(screen.getByRole("button", { name: "Accept" })).toBeTruthy();                    // the one suggestion, below
});

it("the situation bar names the destination, how it was set, and whether the ETA is the road route or the crew's", () => {
  const until = new Date(Date.now() + 9 * 60000).toISOString();
  show(transport({ destination: heardRsj, eta: { source: "route", until } }),
    { clocks: [...base.clocks.filter((c) => c.id !== "eta"), { id: "eta", label: "ETA", seconds: 540, until, source: "route" }] });
  render(<SituationBar />);
  expect(screen.getByLabelText(`Destination ${RSJ}, heard “Regional”, 9 minutes by road`)).toBeTruthy();
  expect(screen.getByText("road route")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Accept" })).toBeNull();
  cleanup();
  show(transport({ destination: { ...heardRsj, how: "suggested", said: null } }),
    { clocks: [...base.clocks.filter((c) => c.id !== "eta"), { id: "eta", label: "ETA", seconds: 720, until, source: "crew" }] });
  render(<SituationBar />);
  expect(screen.getByText("Herald suggested, accepted")).toBeTruthy();
  expect(screen.getByText("crew estimate")).toBeTruthy();
});

it("no dropdown in the main flow: only the small Other hospital link opens the county list", () => {
  render(<><SituationBar /><EdCard onHandoff={() => {}} /></>);
  expect(screen.queryByRole("button", { name: /choose destination|set destination|change/i })).toBeNull();
  expect(screen.getByText(/Say the hospital, or accept Herald’s suggestion/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Other hospital…" }));
  expect(useHerald.getState().ui.destinationOpen).toBe(true);
  // and nothing else in the app opens it
  const files: string[] = [];
  const walk = (dir: string) => readdirSync(dir).forEach((n) => { const p = join(dir, n);
    if (statSync(p).isDirectory()) { if (n !== "test") walk(p); } else if (/\.tsx?$/.test(n)) files.push(p); });
  walk("src");
  expect(files.filter((f) => readFileSync(f, "utf8").includes("destinationOpen: true"))).toEqual(["src/features/transport/DestinationStatus.tsx"]);
});

it("the Other hospital list shows the county's hospitals nearest first with drive time and stroke designations", async () => {
  const set = vi.spyOn(api, "setDestination").mockResolvedValue(true);
  useHerald.getState().setUi({ destinationOpen: true });
  render(<DestinationDialog />);
  const rows = Array.from(document.querySelectorAll(".destination-row"));
  expect(rows.map((r) => r.querySelector(".destination-name")!.textContent)).toEqual([RSJ, "Santa Clara Valley Medical Center"]);
  expect(screen.getByText("9 min · 6.1 km")).toBeTruthy();
  expect(document.querySelector(".destination-tag[data-relevant]")!.textContent).toMatch(/Stroke Center/);
  expect(screen.getByText(/Diversion and bed status are not available/)).toBeTruthy();   // Herald does not know it
  fireEvent.click(rows[1]);
  await waitFor(() => expect(set).toHaveBeenCalledWith("VMC", "list"));
  expect(useHerald.getState().ui.destinationOpen).toBe(false);
});

it("says why there are no drive times instead of showing guesses", () => {
  expect(routingNote(transport({ routing: false }))).toMatch(/not set up/);
  expect(routingNote(transport({ position: null }))).toMatch(/shares its location/);
  expect(routingNote(transport({ position: { at: "x", accuracy_m: 5, fresh: false } }))).toMatch(/out of date/);
  expect(routingNote(transport({ router_error: "ConnectError" }))).toMatch(/unavailable/);
  expect(routingNote(transport())).toBeNull();
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

it("a tablet that is not moving still reports its position on a timer, with the fix's age by its own clock", async () => {
  // live report 2026-09-26: watchPosition fired once, the destination was set minutes later, the ETA stayed the crew's
  vi.useFakeTimers();
  const fetchMock = vi.fn().mockResolvedValue(new Response("{}"));
  vi.stubGlobal("fetch", fetchMock);
  const fix = (): GeolocationPosition => ({ timestamp: Date.now() - 500, toJSON: () => ({}),
    coords: { latitude: 37.3352, longitude: -121.8811, accuracy: 35 } as GeolocationCoordinates });
  const geo = { watchPosition: vi.fn((ok: PositionCallback) => { ok(fix()); return 1; }), clearWatch: vi.fn(),
    getCurrentPosition: vi.fn((ok: PositionCallback) => ok(fix())) };
  vi.stubGlobal("navigator", { ...navigator, geolocation: geo });
  useHerald.setState({ captureElsewhere: false });
  const { result, unmount } = renderHook(() => useVehicleLocation());
  expect(result.current).toBe("sharing");
  expect(fetchMock).toHaveBeenCalledTimes(1);                                   // the one watch callback
  await act(async () => { vi.advanceTimersByTime(EVERY_MS * 4); });
  expect(geo.getCurrentPosition).toHaveBeenCalledTimes(4);
  expect(fetchMock).toHaveBeenCalledTimes(5);                                   // and one per timed re-read
  const body = JSON.parse(fetchMock.mock.calls[4][1].body);
  expect(body).toMatchObject({ lat: 37.3352, lon: -121.8811, accuracy_m: 35, age_s: 0.5 });
  unmount();
  expect(geo.clearWatch).toHaveBeenCalled();
});
