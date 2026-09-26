import { readFileSync } from "node:fs";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HandoffPage } from "@/pages/HandoffPage";
import { initialUi, useHerald } from "@/lib/store";
import { parseFixture } from "@/lib/ws";
import type { Snapshot } from "@/lib/types";

vi.mock("@/lib/contract", () => ({
  useContract: () => ({ keys: {}, relayTiers: {}, changeRules: {} }), label: (_: unknown, key: string) => key,
}));
const snapshot = (parseFixture(readFileSync("public/fixtures/stroke_demo.jsonl", "utf8")).at(-1)!.msg as { state: Snapshot }).state;
beforeEach(() => {
  // no server: the page must still render its one report and never guess
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, json: async () => ({}) })));
  useHerald.setState({ source: "live", conn: "open", stale: false, pending: {}, ui: initialUi("") });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function caughtUp(s: Snapshot) {
  s.relay = {
    ...s.relay, configured: true, link: "good", pending: [],
    authorized: { destination: "Valley Medical", scope: "stroke pre-alert set", at: "now" },
    sync: Object.fromEntries(Object.keys(s.relay.sync).map((k) => [k, "sent"])),
    log: [{ ts: "now", seq: 1, tier: "full", bytes: 100, keys: [], why: [], removed: [], queued_after: 0, result: "acked", patient: s.incident.id }],
  };
}

describe("handoff claims", () => {
  it("keeps unverified values out of the report even after earlier technical delivery, and lists them to confirm", () => {
    const s = structuredClone(snapshot);
    s.facts["complaint.chief"] = { ...Object.values(s.facts)[0], key: "complaint.chief", label: "Chief complaint", value: "UNVERIFIED-COMPLAINT", status: "unconfirmed" };
    useHerald.setState({ snapshot: s, source: "fixture" });
    render(<HandoffPage />);
    const report = screen.getByRole("region", { name: "Handoff report" });
    expect(report.textContent).not.toContain("UNVERIFIED-COMPLAINT");
    // sources disagree in this recording, so the conflict shows at once and the rest is one tap away
    expect(screen.getByRole("region", { name: "Sources disagree · pick one" })).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Not confirmed · stays out of the report" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /^Show the other (1 item|\d+ items)$/ }));
    const left = screen.getByRole("region", { name: "Not confirmed · stays out of the report" });
    expect(within(left).getByText("UNVERIFIED-COMPLAINT")).toBeTruthy();
    expect(screen.queryByText("Complete")).toBeNull();
  });
  it("keeps the report and its export available without a receiving link", () => {
    useHerald.setState({ snapshot: { ...snapshot, relay: { ...snapshot.relay, configured: false } }, source: "fixture" });
    render(<HandoffPage />);
    expect(screen.getByRole("region", { name: "Handoff report" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Export report as text" })).toBeTruthy();
    expect(screen.getByText("No receiving link · the report stays on this vehicle")).toBeTruthy();
  });
  it("shows a reconciled counter with a real duplicate count in the detailed view once the ED is caught up (P3.2)", () => {
    const s = structuredClone(snapshot);
    caughtUp(s);
    s.relay.duplicates_acked = 2;
    useHerald.setState({ snapshot: s, ui: { ...initialUi(""), mode: "explain" } });
    render(<HandoffPage />);
    expect(screen.getByText(/reconciled · 2 duplicates/)).toBeTruthy();
  });
  it("omits the duplicate count, rather than guessing, when an older snapshot predates the field", () => {
    const s = structuredClone(snapshot);
    caughtUp(s);
    delete s.relay.duplicates_acked;
    useHerald.setState({ snapshot: s, ui: { ...initialUi(""), mode: "explain" } });
    render(<HandoffPage />);
    expect(screen.getByRole("region", { name: "Handoff report" })).toBeTruthy();
    expect(screen.queryByText(/reconciled ·/)).toBeNull();
  });
  it("shows the recorded scenario's report in replay mode, not an unavailable notice", () => {
    useHerald.setState({ snapshot: structuredClone(snapshot), source: "fixture" });
    render(<HandoffPage />);
    expect(screen.getAllByRole("region", { name: "Handoff report" })).toHaveLength(1);
    expect(screen.queryByText(/does not include a full handoff report/)).toBeNull();
    expect(screen.queryByText(/Loading report/)).toBeNull();
  });
  it("says so, with a retry, when the live report cannot load", async () => {
    useHerald.setState({ snapshot: structuredClone(snapshot) });
    render(<HandoffPage />);
    expect(await screen.findByText(/Could not load the handoff/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });
});
