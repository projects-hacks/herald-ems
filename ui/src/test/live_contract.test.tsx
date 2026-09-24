// The screens against a real snapshot captured from the server on 2026-09-24 (run E v2, every call type): a fall with
// chest pain, medications given (records), two open checklists (STEMI and trauma), county scores. Guards the UI
// against the contract as it is now, not as it was when the screens were written (UX_PLAN §5.6).
import { readFileSync } from "node:fs";
import { beforeEach, describe, expect, it } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { formatRecord, formatValue } from "@/lib/format";
import { initialUi, useHerald } from "@/lib/store";
import type { Snapshot } from "@/lib/types";
import { PreAlertCard } from "@/features/overview/PreAlertCard";
import { TraceEntry } from "@/features/trace/trace";

const live: Snapshot = JSON.parse(readFileSync("src/test/fixtures/live_every_call.json", "utf8"));

describe("records (medications given, procedures)", () => {
  it("read as a paramedic would say them, never [object Object]", () => {
    expect(formatRecord({ drug: "fentanyl", dose: 50, unit: "mcg", route: "IV", time: "1422", by: "crew" }))
      .toBe("fentanyl 50 mcg IV at 1422");
    expect(formatRecord({ drug: "naloxone", dose: 2, route: "IN", by: "fire" })).toBe("naloxone 2 IN · by fire");
    expect(formatRecord({ drug: "nitroglycerin", dose: 0.4, route: "SL", count: 3 })).toBe("nitroglycerin 0.4 SL · ×3");
    expect(formatRecord({ procedure: "iv access", detail: "18 gauge left AC", by: "crew" })).toBe("iv access · 18 gauge left AC");
    for (const e of Object.values(live.events ?? {}).flat()) expect(formatValue(e.value)).not.toContain("[object");
  });
  it("the snapshot lists every medication given, in order", () => {
    expect(live.events?.["meds.given"].map((e) => (e.value as Record<string, string>).drug)).toEqual(["naloxone", "aspirin", "fentanyl"]);
  });
});

describe("screens on the live snapshot", () => {
  beforeEach(() => useHerald.setState({ snapshot: null, pending: {}, ui: initialUi("") }));

  it("the pre-alert card switches between the open checklists", () => {
    useHerald.getState().setSnapshot(live);
    render(<PreAlertCard />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(live.readiness.map((r) => `${r.label} ${r.done}/${r.total}`));
    fireEvent.click(tabs[1]);
    expect(screen.getByText(live.readiness[1].label, { selector: "#pa-h, #pa-h *" })).toBeTruthy();
  });

  it("trace cards show the model step only (no rules extractor), and records as text", () => {
    useHerald.getState().setSnapshot(live);
    for (const t of live.transcripts) {
      const { container, unmount } = render(<TraceEntry t={t} wide />);
      expect(container.textContent).not.toMatch(/Rules ·|rules only|\[object/);
      unmount();
    }
  });
});
