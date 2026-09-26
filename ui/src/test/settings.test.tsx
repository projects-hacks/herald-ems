// Settings holds only what the medic sets for themselves and what this vehicle runs (owner review, 2026-09-26).
// Theme and Patients are header controls; the guided demo and the explain view are presenter tools.
import { readFileSync } from "node:fs";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CabinApp } from "@/features/cabin/CabinApp";
import { initialUi, useHerald } from "@/lib/store";
import { parseFixture } from "@/lib/ws";
import type { Snapshot } from "@/lib/types";

const base = (parseFixture(readFileSync("public/fixtures/stroke_demo.jsonl", "utf8"))[0].msg as { state: Snapshot }).state;
vi.mock("@/lib/contract", () => ({ useContract: () => ({ keys: {}, relayTiers: {}, changeRules: {} }) }));

function openSettings() {
  useHerald.setState({ snapshot: base, source: "live", stale: false, conn: "open", ui: initialUi("") });
  render(<CabinApp />);
  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  return screen.getByRole("region", { name: "Settings" });
}

describe("settings", () => {
  beforeEach(() => { Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn() } }); });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it("has no duplicates of header controls and no presenter tools", () => {
    const page = openSettings();
    for (const name of [/theme/i, /Patients/, /Guided demo/, /Detailed application view/])
      expect(within(page).queryByRole("button", { name })).toBeNull();
  });

  it("sets text size and reduced motion", () => {
    const page = openSettings();
    fireEvent.click(within(within(page).getByRole("group", { name: "Text size" })).getByRole("button", { name: "Text 125%" }));
    expect(useHerald.getState().ui.typeScale).toBe(1.25);
    fireEvent.click(within(page).getByRole("checkbox", { name: "Reduce motion" }));
    expect(useHerald.getState().ui.reducedMotion).toBe(true);
  });

  it("turns automatic capture off, so calls start paused", () => {
    const page = openSettings();
    fireEvent.click(within(page).getByRole("checkbox", { name: /Listen and watch automatically/ }));
    expect(useHerald.getState().ui.autoCapture).toBe(false);
    expect(useHerald.getState().ui.capturePaused).toBe(true);
  });

  it("states the privacy rules plainly and names the county protocols in use", () => {
    const page = openSettings();
    expect(within(page).getByRole("region", { name: "Recording and privacy" }).textContent).toContain("until you confirm it");
    expect(within(page).getByRole("region", { name: "This vehicle" }).textContent).toContain(base.county.name);
  });
});
