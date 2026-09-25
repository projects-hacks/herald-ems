import { readFileSync } from "node:fs";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { CaptureControl } from "@/features/capture/CaptureControl";
import { MismatchCard } from "@/features/capture/MismatchCard";
import { useHerald } from "@/lib/store";
import { needsTap } from "@/lib/selectors";
import type { FactView, Snapshot } from "@/lib/types";

const original: Snapshot = JSON.parse(readFileSync("src/test/fixtures/live_every_call.json", "utf8"));
let snapshot: Snapshot;
let dose: FactView;
beforeEach(() => {
  snapshot = structuredClone(original);
  snapshot.capture = { auto: false, source: "browser", sees: "off", incident_id: snapshot.incident.id,
    fps_in: 1, roi: null, last: null, counts: { frames: 0, gated: 0, captured: 0, stored: 0 }, pending: 0, error: null };
  dose = { ...snapshot.events!["meds.given"][0], status: "unconfirmed",
    verify: { status: "mismatch", label_drug: "ondansetron", photo_id: null, resolution: null } };
  useHerald.setState({ snapshot, source: "live", conn: "open", stale: false });
  vi.stubGlobal("fetch", vi.fn(async (path: string) => ({ ok: true, json: async () => path === "/api/state" ? snapshot : {} })));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("does not start capture on mount; Show Herald explicitly posts with patient identity", async () => {
  render(<CaptureControl />);
  expect(fetch).not.toHaveBeenCalled();
  expect(screen.getByRole("status").textContent).toContain("off");
  fireEvent.click(screen.getByRole("button", { name: "Show Herald" }));
  await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/capture/now", expect.objectContaining({
    body: JSON.stringify({ incident_id: snapshot.incident.id }), method: "POST" })));
});
it.each(["fixture", "stale", "disconnected"])("blocks mutations when %s", (condition) => {
  useHerald.setState(condition === "fixture" ? { source: "fixture" } : condition === "stale" ? { stale: true } : { conn: "closed" });
  render(<><CaptureControl /><ul><MismatchCard fact={dose} /></ul></>);
  for (const name of ["Show Herald", "Turn auto on", "Keep as said", "Edit"]) {
    expect((screen.getByRole("button", { name }) as HTMLButtonElement).disabled).toBe(true);
  }
  expect(fetch).not.toHaveBeenCalled();
});
it("keeps older dose mismatches in the queue even when a newer dose exists", () => {
  snapshot.events!["meds.given"][0] = dose;
  expect(needsTap(snapshot).some((f) => f.id === dose.id)).toBe(true);
});
it("editing requires a typed correction and preserves other dose fields", async () => {
  render(<ul><MismatchCard fact={dose} /></ul>);
  fireEvent.click(screen.getByRole("button", { name: "Edit" }));
  expect(fetch).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Correct recorded drug"), { target: { value: "ondansetron" } });
  fireEvent.click(screen.getByRole("button", { name: "Save correction & confirm" }));
  await waitFor(() => expect(fetch).toHaveBeenCalledWith(`/api/capture/verify/${dose.id}`, expect.objectContaining({
    body: JSON.stringify({ action: "edit", value: { ...(dose.value as object), drug: "ondansetron" }, incident_id: snapshot.incident.id }) })));
});
