import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { activity, liveHeard, markWords, patientLine, presence, readingCards, readingText, setAside, speakerOf } from "@/lib/copilot";
import { UNIDENTIFIED_SPEAKER } from "@/lib/format";
import { needsTap } from "@/lib/selectors";
import { parseFixture } from "@/lib/ws";
import type { FactView, Health, Snapshot } from "@/lib/types";

const base = (parseFixture(readFileSync("public/fixtures/stroke_demo.jsonl", "utf8")).at(-1)!.msg as { state: Snapshot }).state;
const fact = (id: string, key: string, value: number, extra: Partial<FactView> = {}): FactView => ({
  id, key, value, unit: null, label: key, role: "device", speaker: null, captured_by: "camera", confidence: 0.9,
  provenance: { audio_id: null, t_start: null, t_end: null, text: null, photo_id: "p1", crop: null, extractor: null, hold_reason: null, frame_id: "f1" },
  ts: "2026-09-25T14:22:00Z", status: "unconfirmed", previous_value: null, previous_ts: null, ...extra,
});
const withReading = (): Snapshot => {
  const facts = [fact("a", "vitals.hr", 112), fact("b", "vitals.sbp", 168), fact("c", "vitals.dbp", 94), fact("d", "vitals.spo2", 93)];
  return { ...base, timeline: [...base.timeline, ...facts], facts: { ...base.facts, ...Object.fromEntries(facts.map((f) => [f.key, f])) },
    capture_groups: [{ frame_id: "f1", trigger: "monitor", photo_id: "p1", ts: "2026-09-25T14:22:00Z", batch_fact_ids: ["a", "b", "c", "d"], individual: [] }] };
};

describe("copilot screen selectors", () => {
  it("writes a monitor reading the way a clinician does, blood pressure paired", () => {
    expect(readingText([fact("a", "vitals.hr", 112), fact("b", "vitals.sbp", 168), fact("c", "vitals.dbp", 94)])).toBe("HR 112 · BP 168/94");
  });
  it("offers one reading card per frame and does not ask for its values again one by one", () => {
    const s = withReading();
    const cards = readingCards(s);
    expect(cards).toHaveLength(1);
    expect(cards[0].text).toBe("HR 112 · BP 168/94 · SpO₂ 93");
    expect(cards[0].batchIds).toEqual(["a", "b", "c", "d"]);
    expect(needsTap(s).some((f) => ["a", "b", "c", "d"].includes(f.id))).toBe(false);
  });
  it("reads a snapshot without capture groups (older vehicle, recorded fixture) as nothing batched", () => {
    expect(readingCards({ ...base, capture_groups: undefined })).toEqual([]);
  });
  it("reports what Herald did as clinical outcomes, newest first, and never telemetry", () => {
    const lines = activity(withReading(), 20);
    expect(lines.some((l) => l.kind === "read" && l.text.startsWith("Read the monitor — HR 112"))).toBe(true);
    expect(lines.some((l) => l.kind === "heard")).toBe(true);
    const sent = lines.filter((l) => l.kind === "sent").map((l) => l.text);
    expect(new Set(sent).size).toBe(sent.length);   // a re-sent picture is not news
    for (let i = 1; i < lines.length; i++) expect(lines[i - 1].ts >= lines[i].ts).toBe(true);
    for (const l of lines) expect(l.text).not.toMatch(/confidence|%|frame|gate|queue|model/i);
  });
  it("names a known speaker in a heard line and leaves an unidentified one out", () => {
    const t = base.transcripts.find((x) => x.captured_by !== "camera" && x.captured_by !== "device" && x.trace?.model?.status !== "error" && (x.trace?.model?.facts?.length ?? 0) > 0)!;   // words that gave facts
    const heard = (speaker: string | null) =>
      activity({ ...base, transcripts: [{ ...t, speaker, text: "pulse 92" }] }, 200).find((l) => l.kind === "heard")!.text;
    expect(heard("daughter")).toBe("Heard daughter: “pulse 92”");
    expect(heard(UNIDENTIFIED_SPEAKER)).toBe("Heard “pulse 92”");
  });
  it("keeps the whole system status to one pill that only turns red when something stopped", () => {
    const ok = { replay: false, offline: false, hasSnapshot: true, health: { llm_available: true } as Health, listening: true, micError: null, monitorWatching: true, cameraError: null };
    expect(presence(ok)).toEqual({ tone: "ok", text: "Listening · watching the monitor" });
    expect(presence({ ...ok, listening: false, monitorWatching: false }).tone).toBe("idle");
    expect(presence({ ...ok, micError: "Microphone needs HTTPS or localhost." })).toEqual({ tone: "down", text: "Microphone blocked by the browser — open Herald via localhost" });
    expect(presence({ ...ok, health: { llm_available: false } as Health }).text).toMatch(/not becoming facts/);
    expect(presence({ ...ok, offline: true }).tone).toBe("down");
    expect(presence({ ...ok, replay: true }).tone).toBe("replay");
  });
  it("builds the patient line from confirmed facts only", () => {
    const eta = { ...fact("e", "transport.eta_min", 12, { status: "confirmed" }), label: "ETA" };
    const pending = { ...fact("g", "transport.destination", 0, { status: "unconfirmed" }), value: "Regional CSC" } as FactView;
    const line = patientLine({ ...base, facts: { ...base.facts, "transport.eta_min": eta, "transport.destination": pending } });
    expect(line).not.toContain("ETA");                    // the ETA counts down in the situation bar only: one ETA on screen
    expect(line).not.toContain("Regional CSC");            // an unconfirmed destination is not stated
    const sure = { ...pending, status: "confirmed" } as FactView;
    expect(patientLine({ ...base, facts: { ...base.facts, "transport.destination": sure } })).toMatch(/[^·] → Regional CSC$/);
  });
});

describe("Herald live", () => {
  const entry = (over: object) => ({ id: "t9", ts: "2026-09-25T14:30:00Z", text: "She takes warfarin, five milligrams.", captured_by: "other",
    speaker: "husband", audio_id: "a1", fact_ids: ["w1"], extract: { rules: 0, llm: 1, ms: 400 },
    trace: { heard: { text: "" }, rules: { ms: 0, facts: [] },
      model: { status: "done", facts: [{ id: "w1", key: "meds.anticoagulant", label: "Anticoagulant", value: "warfarin", role: "family", speaker: "husband",
        status: "unconfirmed", confidence: 0.9, extractor: "llm", relay: "held", hold_reason: null }] },
      effects: { readiness: [{ label: "Stroke alert", from: 2, to: 3, total: 6, ready: false }], alerts_new: [], scores: [], gaps_closed: [] } },
    ...over }) as unknown as Snapshot["transcripts"][number];
  it("shows the newest words, marks the value taken from them, and names what it changed", () => {
    const live = liveHeard({ ...base, transcripts: [...base.transcripts, entry({})] })!;
    expect(live.who).toBe("husband");
    expect(live.chips).toEqual([expect.objectContaining({ label: "Anticoagulant", value: "warfarin" })]);
    expect(live.effects).toEqual(["Stroke alert 3 of 6"]);
    expect(live.segments.filter((g) => g.hl).map((g) => g.t)).toEqual(["warfarin"]);
  });
  it("says it is still understanding while the model runs, with no chips yet", () => {
    const e = entry({}); (e.trace.model as { status: string; facts?: unknown[] }) = { status: "running" };
    const live = liveHeard({ ...base, transcripts: [...base.transcripts, e] })!;
    expect(live.working).toBe(true); expect(live.chips).toEqual([]);
  });
  it("keeps chatter out of the live view and the feed, and counts it as set aside", () => {
    const chatter = entry({ id: "t10", ts: "2026-09-25T14:31:00Z", text: "They carried it, so they want two spoons.", fact_ids: [] });
    (chatter.trace.model as { facts?: unknown[] }).facts = [];
    const s = { ...base, transcripts: [...base.transcripts, entry({}), chatter] };
    expect(liveHeard(s)!.id).toBe("t9");                                   // the last words that mattered
    expect(activity(s, 50).some((l) => l.text.includes("two spoons"))).toBe(false);
    expect(setAside(s)).toBeGreaterThanOrEqual(1);
  });
  it("never names an unidentified ambient speaker or the medic", () => {
    expect(speakerOf({ speaker: "Ambient audio · speaker unverified" })).toBeNull();
    expect(speakerOf({ speaker: "Speaker not identified" })).toBeNull();
    expect(speakerOf({ speaker: "medic" })).toBeNull();
  });
  it("marks words case-insensitively and keeps them exactly as heard", () => {
    expect(markWords("BP 182 over 104, Warfarin", ["182", "warfarin"]).map((g) => g.t).join("")).toBe("BP 182 over 104, Warfarin");
    expect(markWords("BP 182 over 104, Warfarin", ["182", "warfarin"]).filter((g) => g.hl).map((g) => g.t)).toEqual(["182", "Warfarin"]);
  });
});
