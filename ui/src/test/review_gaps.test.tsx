import { readFileSync } from "node:fs";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { initialUi, useHerald } from "@/lib/store";
import { alertKey, alertPriority, erRows, needsTap, queuedCount } from "@/lib/selectors";
import type { Alert, Snapshot } from "@/lib/types";
import { AttentionQueue } from "@/features/attention/AttentionQueue";
import { CaptureBar } from "@/features/capture/CaptureBar";
import { PatientPage } from "@/pages/PatientPage";
import { PatientRoster } from "@/components/PatientRoster";
import { CompactStatus } from "@/components/CompactStatus";
import { NewIncidentDialog } from "@/components/GlobalStates";
import { HandoffReport } from "@/features/handoff/HandoffReport";
import { Button } from "@/components/kit";
import { useHotkeys } from "@/hooks/useHotkeys";

const base: Snapshot = JSON.parse(readFileSync("src/test/fixtures/live_every_call.json", "utf8"));
const keys = JSON.parse(readFileSync("public/contract/keys.json", "utf8"));
const contract = { keys, relayTiers: JSON.parse(readFileSync("public/contract/relay_tiers.json", "utf8")), changeRules: {}, checklists: { trauma: { label: "Trauma" } } };
vi.mock("@/lib/contract", () => ({ useContract: () => contract, label: (_c: unknown, key: string) => keys[key]?.label ?? key }));
let snapshot: Snapshot;
beforeEach(() => {
  snapshot = structuredClone(base);
  useHerald.setState({ snapshot, source: "live", conn: "open", stale: false, pending: {}, health: null, ui: initialUi("") });
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({}) })));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("renders verbatim criteria and county words and ranks red trauma high", () => {
  const trauma: Alert = { type: "trauma_alert_criteria", label: "Trauma Alert criteria met", level: "red", score: "trauma_605", criteria: ["N.3: reviewed county criterion"], county_rule: ["Reviewed county destination wording"], county: "Santa Clara" };
  const sepsis: Alert = { type: "sepsis_prenotification", label: "Sepsis pre-notification", level: "notify", score: "sepsis_700a04", criteria: ["Reviewed sepsis criterion"] };
  snapshot.alerts = [sepsis, trauma];
  render(<AttentionQueue />);
  expect(alertPriority(trauma)).toBe("high"); expect(alertPriority(sepsis)).toBe("medium");
  expect(alertKey(trauma)).not.toBe(alertKey({ ...trauma, criteria: ["different"] }));
  expect(screen.getByText(trauma.criteria[0])).toBeTruthy();
  expect(screen.getByText(/Reviewed county destination wording/)).toBeTruthy();
  expect(screen.getByText(sepsis.criteria[0])).toBeTruthy();
});
it("submits a typed note with patient identity and source", async () => {
  render(<CaptureBar />);
  fireEvent.change(screen.getByLabelText("Spoken or typed note"), { target: { value: "Heart rate 95" } });
  fireEvent.click(screen.getByRole("button", { name: "Submit note" }));
  await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/transcript", expect.objectContaining({
    headers: expect.objectContaining({ "X-Herald-Patient": snapshot.incident.id }), body: JSON.stringify({ text: "Heart rate 95", captured_by: "medic", speaker: null }) })));
});
it("submits typed monitor readings as device facts and exposes failures", async () => {
  vi.mocked(fetch).mockResolvedValue({ ok: false, status: 400, json: async () => ({ detail: "Reading outside configured range" }) } as Response);
  render(<CaptureBar />);
  fireEvent.change(screen.getByLabelText("Value"), { target: { value: "95" } });
  fireEvent.click(screen.getByRole("button", { name: "Record reading" }));
  await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("Reading outside configured range"));
  expect(fetch).toHaveBeenCalledWith("/api/facts", expect.objectContaining({ body: expect.stringContaining('"captured_by":"device"') }));
});
it("fixture capture controls are disabled and photo link resolves under classic", () => {
  useHerald.setState({ source: "fixture" }); render(<CaptureBar />);
  expect((screen.getByRole("button", { name: /Hold to talk · medic/ }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole("link", { name: /Take a photo/ }).getAttribute("href")).toBe("/capture.html");
  expect(fetch).not.toHaveBeenCalled();
});
it("clears unsent note and monitor drafts when the patient changes", () => {
  render(<CaptureBar />);
  fireEvent.change(screen.getByLabelText("Spoken or typed note"), { target: { value: "Old patient's note" } });
  fireEvent.change(screen.getByLabelText("Value"), { target: { value: "95" } });
  act(() => useHerald.setState({ snapshot: { ...snapshot, incident: { ...snapshot.incident, id: "next-patient" } } }));
  expect((screen.getByLabelText("Spoken or typed note") as HTMLTextAreaElement).value).toBe("");
  expect((screen.getByLabelText("Value") as HTMLInputElement).value).toBe("");
});
it("supplemental oxygen submits a boolean rather than a guessed number", async () => {
  render(<CaptureBar />);
  fireEvent.change(screen.getByLabelText("Monitor reading"), { target: { value: "vitals.on_oxygen" } });
  fireEvent.change(screen.getByLabelText("Value"), { target: { value: "false" } });
  fireEvent.click(screen.getByRole("button", { name: "Record reading" }));
  await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/facts", expect.objectContaining({ body: expect.stringContaining('"value":false') })));
});
it("shows every held dose and its source audio, not just the latest", () => {
  const first = snapshot.events!["meds.given"][0]; first.status = "unconfirmed"; first.provenance.audio_id = "audio-first";
  expect(needsTap(snapshot).some((f) => f.id === first.id)).toBe(true);
  const view = render(<PatientPage />);
  expect(view.container.textContent).toContain("naloxone"); expect(view.container.textContent).toContain("fentanyl");
  expect(view.container.querySelector('audio[src="/api/audio/audio-first"]')).toBeTruthy();
  expect(screen.getAllByRole("button", { name: "Confirm" }).length).toBeGreaterThan(0);
});
it("uses the active patient's relay map and counts no queued keys before authorization", () => {
  snapshot.active_patient = "second"; snapshot.relay.sync = {};
  snapshot.relay.authorized = { destination: "Test ED", scope: "test", at: "now" };
  snapshot.relay.patients = { second: { triage: null, pending: 1, sync: { "vitals.hr": "queued" } }, first: { triage: null, pending: 0, sync: { "vitals.hr": "sent" } } };
  expect(queuedCount(snapshot)).toBe(1);
  expect(erRows(snapshot, contract).find((r) => r.key === "vitals.hr")?.state).toBe("queued");
  snapshot.relay.authorized = null; expect(queuedCount(snapshot)).toBe(0);
});
it("mounts the roster and sends an explicit patient activation", async () => {
  snapshot.patients = [{ id: "one", label: "Driver", triage: null, summary: "", readiness_done: 0, readiness_total: 6 }, { id: "two", label: "Passenger", triage: null, summary: "", readiness_done: 0, readiness_total: 6 }]; snapshot.active_patient = "one";
  render(<PatientRoster />); fireEvent.click(screen.getByRole("button", { name: /Passenger/ }));
  await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/patients/two/activate", expect.anything()));
});
it("new incident submits selected dispatch, not the previous call", async () => {
  useHerald.getState().setUi({ confirmNewIncident: true }); render(<NewIncidentDialog />);
  fireEvent.change(screen.getByLabelText("Dispatch / call type"), { target: { value: "fall" } });
  fireEvent.click(screen.getByRole("button", { name: "Start new incident" }));
  await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/incident", expect.objectContaining({ body: JSON.stringify({ dispatch: "fall" }) })));
});
it("exposes compact model-down and ED offline status", () => {
  snapshot.relay.configured = true; snapshot.relay.authorized = { destination: "ED", scope: "test", at: "now" }; snapshot.relay.link = "down";
  useHerald.setState({ health: { llm_model: "test", llm_available: false, stt_model: "fake", stt_loaded: false, incident: snapshot.incident.id, cloud_ai_calls: 0 } });
  render(<CompactStatus />); expect(screen.getByRole("status").textContent).toContain("Extraction model not running"); expect(screen.getByRole("status").textContent).toContain("ED OFFLINE");
});
it("link hotkey failure creates a visible toast", async () => {
  vi.mocked(fetch).mockRejectedValue(new Error("offline"));
  useHerald.getState().setUi({ page: "settings" });
  function Hotkeys() { useHotkeys(); return null; } render(<Hotkeys />);
  fireEvent.keyDown(window, { key: "D", shiftKey: true });
  await waitFor(() => expect(useHerald.getState().toast?.text).toContain("Link change failed"));
});
it("loads read-aloud report and keeps missing items explicit", async () => {
  vi.mocked(fetch).mockResolvedValue({ ok: true, json: async () => ({ incident: { id: snapshot.incident.id }, as_of: new Date().toISOString(), format: { id: "mist", title: "MIST", label: "MIST" }, formats: [], sections: [{ id: "m", label: "Mechanism", lines: [{ text: "Mechanism not yet known", status: "missing" }] }], not_yet_known: [], not_yet_confirmed: [] }) } as Response);
  render(<HandoffReport />);
  await waitFor(() => expect(screen.getByText("Mechanism not yet known")).toBeTruthy());
  expect(fetch).toHaveBeenCalledWith("/api/handoff", expect.anything());
});
it("uses at least 48 px targets, 64 px for primary buttons", () => {
  const { container } = render(<><Button>Secondary</Button><Button variant="primary">Primary</Button></>);
  expect(within(container).getByText("Secondary").className).toContain("min-h-12");
  expect(within(container).getByText("Primary").className).toContain("min-h-16");
});
