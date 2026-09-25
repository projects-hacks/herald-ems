// U2 acceptance tests (UX_PLAN §7.2): store continuity, stale detection, fixture timing.
import { readFileSync } from "node:fs";
import { beforeEach, describe, expect, it } from "vitest";
import { initialUi, useHerald } from "@/lib/store";
import type { FixtureLine, Snapshot } from "@/lib/types";
import { fixtureDelay, isStale, parseFixture, STALE_MS } from "@/lib/ws";

const lines: FixtureLine[] = parseFixture(readFileSync("public/fixtures/stroke_demo.jsonl", "utf8"));
const states = lines.map((l) => (l.msg as { state: Snapshot }).state);

describe("store", () => {
  beforeEach(() => useHerald.setState({ snapshot: null, pending: {}, ui: initialUi("") }));

  it("keeps a transcript card's position and expanded state when the server updates it in place", () => {
    // find an entry whose model phase goes running -> done between two consecutive messages
    const i = states.findIndex((s, k) => k > 0 && s.transcripts.length > 0 && s.transcripts.length === states[k - 1].transcripts.length
      && s.transcripts.at(-1)!.id === states[k - 1].transcripts.at(-1)!.id
      && JSON.stringify(s.transcripts.at(-1)!.trace.model) !== JSON.stringify(states[k - 1].transcripts.at(-1)!.trace.model));
    expect(i).toBeGreaterThan(0);
    const id = states[i].transcripts.at(-1)!.id;
    useHerald.getState().setSnapshot(states[i - 1]);
    useHerald.getState().toggleExpanded(id);
    const before = useHerald.getState().snapshot!.transcripts.findIndex((t) => t.id === id);
    useHerald.getState().setSnapshot(states[i]);
    expect(useHerald.getState().snapshot!.transcripts.findIndex((t) => t.id === id)).toBe(before);
    expect(useHerald.getState().ui.expanded[id]).toBe(true);
  });

  it("keeps a successful action pending until the next snapshot, then clears it (no optimistic update)", () => {
    useHerald.setState({ pending: { "confirm:f_1": "sent", "reject:f_2": { error: "x" } } });
    useHerald.getState().setSnapshot(states[0]);
    expect(useHerald.getState().pending).toEqual({ "reject:f_2": { error: "x" } });
  });

  it("URL parameters override preferences", () => {
    expect(initialUi("?theme=light&type=1.5&mode=explain&present=1")).toMatchObject({ theme: "light", typeScale: 1.5, mode: "explain", presentationMode: true });
    expect(initialUi("?type=3")).toMatchObject({ typeScale: 1 });
  });
});

describe("stale detection", () => {
  it("flips after 3 s without a message on an open socket", () => {
    expect(isStale(10_000 + STALE_MS - 1, "open", 10_000, true)).toBe(false);
    expect(isStale(10_000 + STALE_MS + 1, "open", 10_000, true)).toBe(true);
  });
  it("is stale when the socket closed after data arrived, not before", () => {
    expect(isStale(0, "closed", 0, true)).toBe(true);
    expect(isStale(0, "closed", 0, false)).toBe(false);
    expect(isStale(0, "connecting", 0, false)).toBe(false);
  });
});

describe("fixture player", () => {
  it("replays with the recorded gaps divided by the speed", () => {
    const gap = lines[5].t_ms - lines[4].t_ms;
    expect(fixtureDelay(lines, 0, 1)).toBe(0);
    expect(fixtureDelay(lines, 5, 1)).toBe(gap);
    expect(fixtureDelay(lines, 5, 4)).toBeCloseTo(gap / 4);
  });
  it("the stroke fixture ends with the checklist ready and every field sent", () => {
    const last = states.at(-1)!;
    expect(last.readiness[0]).toMatchObject({ done: 6, total: 6, ready: true });
    expect(Object.values(last.relay.sync).every((v) => v === "sent")).toBe(true);
  });
});

describe("push-to-talk hold", () => {
  it("records the arrival mark on press and clears it on release", () => {
    useHerald.setState({ alertArrival: { a: 1, b: 2 }, holdMark: null, ui: initialUi("") });
    useHerald.getState().holdAlerts(true);
    expect(useHerald.getState()).toMatchObject({ holdMark: 2, ui: { heldAlerts: true } });
    useHerald.getState().holdAlerts(false);
    expect(useHerald.getState()).toMatchObject({ holdMark: null, ui: { heldAlerts: false } });
  });
});
