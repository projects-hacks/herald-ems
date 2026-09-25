import { readFileSync } from "node:fs";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ProtocolCues } from "@/features/copilot/Copilot";
import { useHerald } from "@/lib/store";
import { parseFixture } from "@/lib/ws";
import type { ProtocolCue, Snapshot } from "@/lib/types";

const base = (parseFixture(readFileSync("public/fixtures/stroke_demo.jsonl", "utf8"))[0].msg as { state: Snapshot }).state;
const quote = "3.2. If patient has four (4) points on the G.F.A.S.T stroke screening transport the patient to a Comprehensive Stroke Center.";
const show = (cues: ProtocolCue[]) => { useHerald.setState({ snapshot: { ...base, protocol_cues: cues } }); render(<ProtocolCues onOpen={() => {}} />); };

describe("county protocol cues", () => {
  afterEach(cleanup);
  it("quotes the county's passage verbatim with its citation and effective date", () => {
    show([{ id: "stroke_destination", title: "Stroke destination", query: "q", state: "found", passages: [{ doc: "700-A13", title: "Stroke",
      section: "3.2", heading: null, page: 2, effective: "January 1, 2026", text: quote, shortened: false, text_layer_uncertain: false }] }]);
    expect(screen.getByText(quote)).toBeTruthy();
    expect(screen.getByText(/700-A13 · Stroke §3\.2/)).toBeTruthy();
    expect(screen.getByText(/effective January 1, 2026/)).toBeTruthy();
  });
  it("says when the documents do not cover it, and never shows a guess while searching", () => {
    show([{ id: "sepsis", title: "Sepsis notification", query: "q", state: "not_covered", passages: [] },
          { id: "stemi", title: "STEMI", query: "q", state: "searching", passages: [] }]);
    expect(screen.getByText(/do not cover this/)).toBeTruthy();
    expect(screen.getByText(/Finding the county passage/)).toBeTruthy();
    expect(screen.queryByRole("blockquote")).toBeNull();
  });
  it("renders nothing when no situation is recognised", () => {
    show([]);
    expect(screen.queryByText("County protocol")).toBeNull();
  });
});
