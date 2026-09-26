// The hand over moment: what is left (never blocking), one report, the hand over itself, and the done state.
import { readFileSync } from "node:fs";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HandoffPage } from "@/pages/HandoffPage";
import { CabinApp } from "@/features/cabin/CabinApp";
import { handoverDelivery, handoverDue, patientIdentity, preAlertStatus } from "@/lib/handover";
import { initialUi, useHerald } from "@/lib/store";
import type { HandoffReportData, Snapshot } from "@/lib/types";

const base: Snapshot = JSON.parse(readFileSync("src/test/fixtures/live_every_call.json", "utf8"));
const keys = JSON.parse(readFileSync("public/contract/keys.json", "utf8"));
const contract = { keys, relayTiers: JSON.parse(readFileSync("public/contract/relay_tiers.json", "utf8")), changeRules: {}, checklists: {} };
vi.mock("@/lib/contract", () => ({ useContract: () => contract, label: (_c: unknown, key: string) => keys[key]?.label ?? key }));

let snapshot: Snapshot;
let report: HandoffReportData;
let fetchMock: ReturnType<typeof vi.fn>;
const posts = () => fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === "POST")
  .map(([url, init]) => [url, (init as RequestInit).body ?? null]);

function makeReport(s: Snapshot, notObtained: string[] = []): HandoffReportData {
  const gaps = [{ key: "allergies", label: "Allergies" }, { key: "symptom.onset", label: "Symptom onset" }];
  return {
    incident: { id: s.incident.id }, as_of: s.incident.started, text: "M: fall. I: none known.",
    format: { id: "mist", label: "MIST", title: "MIST handoff" }, formats: [{ id: "mist", label: "MIST" }, { id: "sbar", label: "Medical" }],
    sections: [
      { id: "m", label: "Mechanism", lines: [{ text: "Ground-level fall", status: "confirmed" }] },
      { id: "i", label: "Injuries", lines: [{ text: "Injuries not yet known", status: "missing" }] },
      { id: "h", label: "History", lines: notObtained.includes("allergies") ? [{ text: "Allergies", status: "not_obtained" }] : [] },
    ],
    not_yet_known: gaps.filter((g) => !notObtained.includes(g.key)), not_yet_confirmed: [],
    not_obtained: gaps.filter((g) => notObtained.includes(g.key)),
  };
}

function authorized(s: Snapshot, sync: "sent" | "queued" = "sent") {
  s.relay = { ...s.relay, configured: true, link: "good", pending: [],
    authorized: { destination: "Regional", scope: "pre-alert", at: s.incident.started },
    sync: Object.fromEntries(Object.keys(s.relay.sync).map((k) => [k, sync])) };
}

beforeEach(() => {
  snapshot = structuredClone(base);
  report = makeReport(snapshot);
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/state") return { ok: true, json: async () => snapshot };
    if (url === "/api/handoff/not-obtained") {
      const body = JSON.parse(String(init?.body));
      report = makeReport(snapshot, body.on ? [body.key] : []);
      return { ok: true, json: async () => report };
    }
    if (url.startsWith("/api/handoff")) return { ok: true, json: async () => report };
    return { ok: true, json: async () => ({}) };
  });
  vi.stubGlobal("fetch", fetchMock);
  useHerald.setState({ snapshot, source: "live", conn: "open", stale: false, pending: {}, health: null, ui: initialUi("") });
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn() } });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("before you hand over", () => {
  it("lists what is left with a count that never blocks the hand over", async () => {
    render(<HandoffPage />);
    const left = await screen.findByRole("region", { name: "Before you hand over" });
    // 5 unconfirmed facts (grouped into rows by sentence) + 2 required items the report lacks
    await waitFor(() => expect(within(left).getByRole("status").textContent).toMatch(/\d+ items left — you can hand over anyway/));
    expect(within(left).getByText("Symptom onset")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Hand over" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("confirms an unconfirmed fact with the same endpoint as Needs you", async () => {
    render(<HandoffPage />);
    const left = await screen.findByRole("region", { name: "Before you hand over" });
    const complaint = snapshot.facts["complaint.chief"];
    const row = within(left).getAllByText((_, el) => el?.tagName === "LI" && !!el.textContent?.includes(String(complaint.value)))[0];
    fireEvent.click(within(row).getAllByRole("button", { name: "Confirm" })[0]);
    await waitFor(() => expect(posts().some(([url]) => String(url).endsWith("/confirm"))).toBe(true));
  });

  it("marks a missing item not obtained, shows it as unable to obtain, and undoes it", async () => {
    render(<HandoffPage />);
    const left = await screen.findByRole("region", { name: "Before you hand over" });
    await within(left).findByText("Allergies");
    const row = within(left).getByText("Allergies").closest("li")!;
    expect(within(row).getByRole("button", { name: "Add Allergies" })).toBeTruthy();
    fireEvent.click(within(row).getByRole("button", { name: "Not obtained" }));
    await waitFor(() => expect(posts()).toContainEqual(["/api/handoff/not-obtained", JSON.stringify({ key: "allergies", on: true })]));
    const settled = await within(left).findByRole("region", { name: "Unable to obtain" });
    expect(within(settled).getByText("Allergies")).toBeTruthy();
    // the report line reads "unable to obtain" too
    expect(within(screen.getByRole("region", { name: "Handoff report" })).getByText("unable to obtain")).toBeTruthy();
    fireEvent.click(within(settled).getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(posts()).toContainEqual(["/api/handoff/not-obtained", JSON.stringify({ key: "allergies", on: false })]));
  });
});

describe("the report", () => {
  it("shows one report, from the server, with no second snapshot summary or draft download", async () => {
    render(<HandoffPage />);
    await screen.findByText("Ground-level fall");
    expect(screen.getAllByRole("region", { name: "Handoff report" })).toHaveLength(1);
    expect(screen.queryByText(/Read-aloud handoff/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Download handoff draft" })).toBeNull();
    expect(screen.getByText("Injuries not yet known").getAttribute("data-status")).toBe("missing");
    expect(screen.getByRole("button", { name: "Export report as text" })).toBeTruthy();
  });

  it("switches format with a link-style control, not a dropdown", async () => {
    render(<HandoffPage />);
    await screen.findByText("Ground-level fall");
    expect(screen.queryByRole("combobox")).toBeNull();
    fireEvent.click(within(screen.getByRole("group", { name: "Report format" })).getByRole("button", { name: "Medical" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/handoff?format=sbar", expect.anything()));
  });

  it("builds the report from the recording in a replay, without calling the server", () => {
    useHerald.setState({ source: "fixture" });
    render(<HandoffPage />);
    expect(screen.getAllByRole("region", { name: "Handoff report" })).toHaveLength(1);
    expect(screen.getByText("Handoff summary")).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalledWith(expect.stringMatching(/^\/api\/handoff/), expect.anything());
    // an unconfirmed complaint never appears in the report
    const complaint = String(snapshot.facts["complaint.chief"].value);
    expect(screen.getByRole("region", { name: "Handoff report" }).textContent).not.toContain(complaint);
  });
});

describe("delivery detail", () => {
  it("keeps the delivery table and packet log out of the medic's view", async () => {
    authorized(snapshot);
    render(<HandoffPage />);
    await screen.findByText("Ground-level fall");
    expect(screen.queryByText("Delivery status")).toBeNull();
    expect(screen.queryByText("Technical diagnostics")).toBeNull();
    expect(screen.queryByText("Receipt")).toBeNull();
    expect(screen.getByText(/Pre-alert live · all confirmed updates delivered/)).toBeTruthy();
  });
  it("shows them in the detailed application view", async () => {
    authorized(snapshot);
    useHerald.setState({ ui: { ...initialUi(""), mode: "explain" } });
    render(<HandoffPage />);
    expect(screen.getByText("Delivery status")).toBeTruthy();
    expect(screen.getByText("Technical diagnostics")).toBeTruthy();
  });
  it("has no authorize form on the handoff", () => {
    snapshot.relay = { ...snapshot.relay, configured: true, authorized: null };
    render(<HandoffPage />);
    expect(screen.queryByRole("button", { name: /Authorize pre-alert/ })).toBeNull();
    expect(screen.getByText("Pre-alert not sent")).toBeTruthy();
  });
});

describe("hand over", () => {
  it("asks once, says what happens, and posts the handover with the destination", async () => {
    authorized(snapshot);
    render(<HandoffPage />);
    fireEvent.click(screen.getByRole("button", { name: "Hand over to Regional" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Hand over to Regional?")).toBeTruthy();
    expect(dialog.textContent).toMatch(/\d+ unconfirmed items won't be included/);
    expect(dialog.textContent).toContain("Listening stops and this patient's audio and photos are deleted.");
    expect(posts()).toHaveLength(0);
    fireEvent.click(within(dialog).getByRole("button", { name: "Hand over" }));
    await waitFor(() => expect(posts()).toContainEqual(["/api/encounters/current/handover", JSON.stringify({ destination: "Regional" })]));
  });

  it("cancel posts nothing, and there are no separate arrival, transfer or finish buttons", () => {
    render(<HandoffPage />);
    expect(screen.queryByRole("button", { name: /Record arrival|Record transfer|Finish this encounter/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Hand over" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));
    expect(posts()).toHaveLength(0);
  });

  it("shows the done state with the ED's receipt and starts the next patient", async () => {
    authorized(snapshot);
    const at = new Date().toISOString();
    snapshot.incident = { ...snapshot.incident, handed_over_at: at, transferred_at: at, ended_at: at };
    snapshot.relay.handover = { at, delivered_at: at, received_at: at };
    render(<HandoffPage />);
    expect(screen.getByRole("heading", { name: /Handed over to Regional · \d\d:\d\d/ })).toBeTruthy();
    expect(screen.getByText(/ED received ✓ \d\d:\d\d/)).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Before you hand over" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Hand over/ })).toBeNull();
    expect(screen.queryByRole("region", { name: "Handoff report" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "View handed-over report" }));
    expect(screen.getByRole("region", { name: "Handoff report" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Start next patient" }));
    await waitFor(() => expect(posts()).toContainEqual(["/api/incident", JSON.stringify({ dispatch: null })]));
  });
});

describe("on Now", () => {
  it("has a Hand over button in the header that opens the handoff, prominent once arrived", async () => {
    const { unmount } = render(<CabinApp />);
    const quiet = screen.getByRole("button", { name: "Hand over" });
    expect(quiet.className).not.toContain("primary");
    unmount();
    snapshot.incident = { ...snapshot.incident, arrived_at: new Date().toISOString() };
    useHerald.setState({ snapshot: { ...snapshot } });
    render(<CabinApp />);
    const due = screen.getByRole("button", { name: "Hand over" });
    expect(due.className).toContain("primary");
    fireEvent.click(due);
    expect(await screen.findByRole("region", { name: "Before you hand over" })).toBeTruthy();
  });

  it("does not start listening or the camera on a handed-over patient; the next patient does", async () => {
    const at = new Date().toISOString();
    snapshot.incident = { ...snapshot.incident, handed_over_at: at, transferred_at: at, ended_at: at };
    useHerald.setState({ snapshot: { ...snapshot } });
    render(<CabinApp />);
    expect(screen.getByRole("heading", { name: /Handed over/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Start next patient" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Hand over" })).toBeNull();
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
    act(() => useHerald.getState().setSnapshot({ ...structuredClone(base), incident: { ...base.incident, id: "inc_next", ended_at: null } }));
    await waitFor(() => expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalled());
  });
});

describe("status lines", () => {
  it("says what the ED has in one line", () => {
    const s = structuredClone(base);
    expect(preAlertStatus(s).text).toBe("No receiving link · the report stays on this vehicle");
    s.relay = { ...s.relay, configured: true, authorized: null };
    expect(preAlertStatus(s).text).toBe("Pre-alert not sent");
    authorized(s, "queued");
    s.relay.sync = { "vitals.hr": "queued", "vitals.sbp": "queued", "patient.age": "queued" };
    expect(preAlertStatus(s).text).toBe("3 updates waiting for the link");
    authorized(s);
    s.relay.clinician_acknowledgements = { [s.incident.id]: [{ at: "2026-09-26T00:12:00", status: "received" }] };
    expect(preAlertStatus(s).text).toBe("Pre-alert live · all confirmed updates delivered · ED acknowledged 00:12");
  });
  it("tracks the final report after the hand over", () => {
    const s = structuredClone(base);
    authorized(s);
    s.relay.handover = { at: "2026-09-26T00:10:00", delivered_at: null, received_at: null };
    expect(handoverDelivery(s).text).toBe("Final report waiting for the link");
    s.relay.handover.delivered_at = "2026-09-26T00:11:00";
    expect(handoverDelivery(s).text).toBe("Final report delivered, waiting for the ED");
    s.relay.handover.received_at = "2026-09-26T00:12:00";
    expect(handoverDelivery(s).text).toBe("ED received ✓ 00:12");
  });
  it("names the patient from confirmed facts and knows when the handover is close", () => {
    const s = structuredClone(base);
    expect(patientIdentity(s)).toContain(String(s.facts["patient.age"].value));
    expect(handoverDue(s, Date.now(), Date.now())).toBe(false);
    s.clocks = [...s.clocks, { id: "eta", label: "ETA", seconds: 240, until: "x" }];
    expect(handoverDue(s, Date.now(), Date.now())).toBe(true);
  });
});
