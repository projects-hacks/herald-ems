import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { Contract } from "@/lib/contract";
import { alertKey, attention, erRows, needsTap, rankAlerts, reconciled, strokeScales } from "@/lib/selectors";
import type { Alert, Snapshot } from "@/lib/types";
import { parseFixture } from "@/lib/ws";

const states = parseFixture(readFileSync("public/fixtures/stroke_demo.jsonl", "utf8")).map((l) => (l.msg as { state: Snapshot }).state);
const last = states.at(-1)!;
const contract: Contract = {
  keys: JSON.parse(readFileSync("public/contract/keys.json", "utf8")),
  relayTiers: JSON.parse(readFileSync("public/contract/relay_tiers.json", "utf8")),
  changeRules: JSON.parse(readFileSync("public/contract/change_rules.json", "utf8")),
};

describe("alert order (UX_PLAN §2.3)", () => {
  const high: Alert = { type: "news2_rise", label: "NEWS2", from: 5, to: 8, band: "high" };
  const low: Alert = { type: "news2_rise", label: "NEWS2", from: 1, to: 3, band: "low" };
  const race: Alert = { type: "race_positive", label: "RACE", score: 6 };
  const change: Alert = { type: "significant_change", key: "vitals.hr", label: "Heart rate", series: [80, 110] };
  it("HIGH before MEDIUM before LOW, newest first within a priority", () => {
    expect(rankAlerts([low, race, high, change])).toEqual([high, change, race, low]);
  });
  it("arrival order beats the server's list order within a priority", () => {
    // the server lists alerts by type; the one that arrived last on screen must lead its group
    expect(rankAlerts([change, race], { [alertKey(change)]: 1, [alertKey(race)]: 2 })).toEqual([race, change]);
  });
});

describe("the attention queue (one list for alerts and taps)", () => {
  const high: Alert = { type: "news2_rise", label: "NEWS2", from: 5, to: 8, band: "high" };
  const race: Alert = { type: "race_positive", label: "RACE", score: 6 };
  it("groups the recorded call: sources disagree to choose, model facts to tap, screens to review", () => {
    const a = attention(last, {});
    expect(a.choose.map((x) => x.type)).toEqual(["contradiction"]);
    expect(a.confirmFacts.length).toBeGreaterThan(0);
    expect(a.review.map((x) => x.type).sort()).toEqual(["gfast_positive", "news2_rise", "race_positive"]);
    expect(a.urgent).toEqual([]);
    expect(a.count).toBe(a.choose.length + a.confirmAlerts.length + a.confirmFacts.length + a.review.length);
  });
  it("HIGH is urgent until seen; seen findings move to acknowledged; a disagreement can't be seen away", () => {
    const contra = last.alerts.find((x) => x.type === "contradiction")!;
    const s = { ...last, alerts: [contra, race, high] };
    expect(attention(s, {}).urgent).toEqual([high]);
    const seen = { [alertKey(high)]: true as const, [alertKey(race)]: true as const, [alertKey(contra)]: true as const };
    const a = attention(s, seen);
    expect(a.urgent).toEqual([]);
    expect(a.review).toEqual([]);
    expect(a.acknowledged).toEqual([high, race]);
    expect(a.choose).toEqual([contra]);                       // still waiting on the medic (P10)
  });
  it("while push-to-talk is held, alerts that arrive later wait until release (P4)", () => {
    const contra = last.alerts.find((x) => x.type === "contradiction")!;
    const arrival = { [alertKey(contra)]: 1, [alertKey(race)]: 2 };
    const s = { ...last, alerts: [contra, race] };
    expect(attention(s, {}, arrival, 1).review).toEqual([]);          // RACE arrived after the press
    expect(attention(s, {}, arrival, 1).choose).toEqual([contra]);
    expect(attention(s, {}, arrival, null).review).toEqual([race]);   // released
  });
  it("a code-status confirmation waits for a tap and is never dismissable", () => {
    const f = Object.values(last.facts)[0];
    const code: Alert = { type: "confirm_required", key: "code_status", label: "Code status", confirm_fact_id: f.id, facts: [f] };
    const a = attention({ ...last, alerts: [code] }, { [alertKey(code)]: true });
    expect(a.confirmAlerts).toEqual([code]);
    expect(a.confirmFacts.find((x) => x.id === f.id)).toBeUndefined();   // not listed twice
  });
});

describe("the recorded stroke call", () => {
  it("facts in a contradiction are not repeated in Needs attention", () => {
    const contra = last.alerts.find((a) => a.type === "contradiction") as Extract<Alert, { type: "contradiction" }>;
    const ids = new Set(needsTap(last).map((f) => f.id));
    for (const f of contra.facts) expect(ids.has(f.id)).toBe(false);
  });
  it("Santa Clara's primary stroke scale (G.F.A.S.T.) comes first", () => {
    expect(strokeScales(last).map((x) => x.id)).toEqual(["GFAST", "RACE"]);
  });
  it("ER rows follow relay-tier order; a disputed key is held, not sent", () => {
    const rows = erRows(last, contract);
    const tiers = rows.map((r) => contract.relayTiers[r.key].tier);
    expect(tiers).toEqual([...tiers].sort((a, b) => a - b));
    expect(rows.find((r) => r.key === "alert.readiness")).toMatchObject({ state: "sent" });
    const sent = rows.filter((r) => r.state === "sent");
    expect(sent.every((r) => r.seq === null || typeof r.seq === "number")).toBe(true);
  });
  it("reconciled only once a full sync is acknowledged on a good link with nothing pending", () => {
    expect(reconciled(last)).toBe(true);
    expect(reconciled({ ...last, relay: { ...last.relay, link: "weak" } })).toBe(false);
    expect(reconciled(states[0])).toBe(false);
  });
});

describe("held wins over sent (regression: a disputed allergy must never show as sent)", () => {
  it("an unconfirmed newest value is Held even when an older confirmed value was acknowledged", () => {
    const contra = last.alerts.find((a) => a.type === "contradiction") as Extract<Alert, { type: "contradiction" }>;
    expect(last.facts[contra.key].status).toBe("unconfirmed");
    expect(last.relay.sync[contra.key]).toBe("sent");                       // the husband's value went out
    expect(erRows(last, contract).find((r) => r.key === contra.key)).toMatchObject({ state: "held", held: "disagree" });
  });
});
