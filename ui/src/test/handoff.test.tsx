import { readFileSync } from "node:fs";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HandoffPage } from "@/pages/HandoffPage";
import { useHerald } from "@/lib/store";
import { parseFixture } from "@/lib/ws";
import type { Snapshot } from "@/lib/types";

vi.mock("@/lib/contract", () => ({
  useContract: () => ({ keys: {}, relayTiers: {}, changeRules: {} }), label: (_: unknown, key: string) => key,
}));
const snapshot = (parseFixture(readFileSync("public/fixtures/stroke_demo.jsonl", "utf8")).at(-1)!.msg as { state: Snapshot }).state;
afterEach(cleanup);
describe("handoff claims", () => {
  it("keeps unverified values out of the spoken draft even after earlier technical delivery", () => {
    const s = structuredClone(snapshot);
    s.facts["complaint.chief"] = { ...Object.values(s.facts)[0], key: "complaint.chief", label: "Chief complaint", value: "UNVERIFIED-COMPLAINT", status: "unconfirmed" };
    useHerald.setState({ snapshot: s });
    render(<HandoffPage />);
    const draft = screen.getByRole("region", { name: "Read-aloud handoff" });
    expect(draft.textContent).not.toContain("UNVERIFIED-COMPLAINT");
    expect(within(draft).getByText(/Needs verification:.*Chief complaint/)).toBeTruthy();
    expect(screen.getByText(/Human acknowledgment is not recorded/)).toBeTruthy();
    expect(screen.queryByText("Complete")).toBeNull();
  });
  it("keeps the handoff draft accessible without a receiving link", () => {
    useHerald.setState({ snapshot: { ...snapshot, relay: { ...snapshot.relay, configured: false } } });
    render(<HandoffPage />);
    expect(screen.getByRole("region", { name: "Read-aloud handoff" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Download handoff draft" })).toBeTruthy();
  });
});
