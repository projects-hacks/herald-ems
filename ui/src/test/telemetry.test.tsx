// Settings > On this box: the telemetry the landing page promises (tokens, GPU power and energy, the cloud cost of the
// same work), polled from GET /api/telemetry while Settings is open; honest when there is no box to ask.
import { readFileSync } from "node:fs";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsPage } from "@/features/cabin/SettingsPage";
import { energyPerCall, usd } from "@/lib/telemetry";
import { initialUi, useHerald } from "@/lib/store";
import { parseFixture } from "@/lib/ws";
import type { Snapshot, Telemetry } from "@/lib/types";

const base = (parseFixture(readFileSync("public/fixtures/stroke_demo.jsonl", "utf8"))[0].msg as { state: Snapshot }).state;

// the live shape (GET /api/telemetry on the box, 2026-09-26), trimmed
const live: Telemetry = {
  since_s: 15620, power_w_now: 21.44, power_w_avg_60s: 20.8, gpu_util_pct: 96, energy_wh: 42.051,
  requests: { attributed_energy_wh: 2.09, count: 200, recent: [
    { kind: "stt", duration_s: 2, energy_j: 36, energy_wh: 0.01, watts_avg: 18 },
    { kind: "stt", duration_s: 0.1, energy_j: 0, energy_wh: 0, watts_avg: 0 },
    { kind: "text", duration_s: 1.5, energy_j: 90, energy_wh: 0.025, watts_avg: 60 },
    { kind: "vision", duration_s: 3, energy_j: 150, energy_wh: 0.042, watts_avg: 50 },
  ] },
  tokens: { prompt: 92423, completion: 13581 }, calls: { llm: 178, vision: 45, stt: 175 }, stt_audio_min: 20.97,
  cost: { local_usd: 0.00631, cloud_equivalent_usd: 0.1875, cloud_breakdown: { llm_usd: 0.06168, stt_usd: 0.12582 }, net_savings_usd: 0.1812 },
  cloud_ai_calls: 0,
  model_server: { mean_request_latency_s: 1.184, generation_tok_s_last_30s: 41.25, running: 0 },
  assumptions: { electricity_usd_per_kwh: 0.15, cloud_llm_usd_per_1m_in: 0.3, cloud_llm_usd_per_1m_out: 2.5, cloud_stt_usd_per_min: 0.006,
    sources: { electricity_usd_per_kwh: "rate used by HP's ZGX console", cloud_llm_usd_per_1m_in: "Gemini 2.5 Flash list price",
      cloud_llm_usd_per_1m_out: "Gemini 2.5 Flash list price", cloud_stt_usd_per_min: "OpenAI Whisper API list price" },
    energy_scope: "GPU power from nvidia-smi (whole-module power is not exposed on GB10): a floor" },
};

function box() {
  render(<SettingsPage />);
  return screen.getByRole("region", { name: "On this box" });
}

describe("on this box", () => {
  let reply: () => Promise<{ ok: boolean; json: () => Promise<unknown> }>;
  beforeEach(() => {
    reply = async () => ({ ok: true, json: async () => live });
    vi.stubGlobal("fetch", vi.fn((url: string) => (url === "/api/telemetry" ? reply() : Promise.resolve({ ok: false, json: async () => ({}) }))));
    useHerald.setState({ snapshot: base, source: "live", stale: false, conn: "open", ui: initialUi("") });
  });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });

  it("shows cloud calls, tokens and speed, GPU power and energy, energy per call and the cost with its assumptions", async () => {
    const page = box();
    await within(page).findByText("Every model ran on this box.");
    expect(page.querySelector(".telemetry-cloud-n")!.textContent).toBe("0");
    const stat = (name: string) => within(page).getByText(name, { selector: "dt" }).parentElement!.textContent;
    expect(stat("Tokens in")).toContain("92,423");
    expect(stat("Tokens out")).toContain("13,581");
    expect(stat("Generation speed")).toContain("41.3 tokens/s");
    expect(stat("Mean request time")).toContain("1.18 s");
    expect(stat("Power now")).toContain("21.4 W");
    expect(stat("60 s average")).toContain("20.8 W");
    expect(stat("Energy used")).toBe("Energy used42.05 Whin 4 h 20 min");
    expect(stat("On this box")).toContain("$0.0063");
    expect(stat("Same work in the cloud")).toContain("$0.19");
    const rows = within(within(page).getByRole("table")).getAllByRole("row").slice(1).map((r) => r.textContent);
    expect(rows).toEqual(["Speech to text2 (1 measured)36.0 J18.0 W", "Text model190.0 J60.0 W", "Vision1150.0 J50.0 W"]);
    expect(page.textContent).toContain("Electricity $0.15 per kWh (rate used by HP's ZGX console).");
    expect(page.textContent).toContain("Cloud speech to text $0.0060 per minute (OpenAI Whisper API list price).");
    expect(page.textContent).toContain("a floor");
    for (const el of Array.from(page.querySelectorAll(".telemetry-stat dd:not(.telemetry-note), .telemetry-table td"))) expect(el.className).toContain("num");
  });

  it("polls every few seconds while open, and stops when closed", async () => {
    vi.useFakeTimers();
    const { unmount } = render(<SettingsPage />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    const calls = () => vi.mocked(fetch).mock.calls.filter(([url]) => url === "/api/telemetry").length;
    expect(calls()).toBe(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(calls()).toBe(2);
    unmount();
    await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
    expect(calls()).toBe(2);
  });

  it("renders dashes, not NaN or a crash, when fields are null or missing", async () => {
    reply = async () => ({ ok: true, json: async () => ({ cloud_ai_calls: 0, tokens: null, model_server: { generation_tok_s_last_30s: null }, power_w_now: null, requests: { recent: null } }) });
    const page = box();
    await within(page).findByText("Every model ran on this box.");
    expect(page.textContent).not.toMatch(/NaN|undefined|null/);
    expect(within(page).getByText("Tokens in", { selector: "dt" }).parentElement!.textContent).toBe("Tokens in—this session");
    expect(within(page).getByText("idle in the last 30 s")).toBeTruthy();
    expect(within(page).getByText("No model calls yet.")).toBeTruthy();
  });

  it("says so when the box does not answer", async () => {
    reply = async () => { throw new Error("offline"); };
    const page = box();
    await waitFor(() => expect(within(page).getByRole("status").textContent).toContain("Telemetry is available when Herald is running on the box"));
  });

  it("does not ask in a recorded replay: there is no box behind it", () => {
    useHerald.setState({ source: "fixture" });
    const page = box();
    expect(within(page).getByRole("status").textContent).toBe("Telemetry is available when Herald is running on the box.");
    expect(vi.mocked(fetch).mock.calls.filter(([url]) => url === "/api/telemetry")).toHaveLength(0);
  });

  it("averages energy per call over the measured recent calls of each kind, weighting power by time", () => {
    expect(energyPerCall(live.requests!.recent)[0]).toEqual({ kind: "stt", label: "Speech to text", calls: 2, measured: 1, joules: 36, watts: 18 });
    // a call too short for the power sampler reads 0 J: it is not averaged in, and a kind with none measured says so
    expect(energyPerCall([{ kind: "text", duration_s: 0.1, energy_j: 0 }, { kind: "text", duration_s: 0.2, energy_j: null }])[0])
      .toMatchObject({ calls: 2, measured: 0, joules: null, watts: null });
    expect(energyPerCall([{ kind: "vision", duration_s: 1, energy_j: 5 }, { kind: "later", duration_s: 1, energy_j: 5 }, { kind: "stt", duration_s: 1, energy_j: 5 }])
      .map((r) => r.label)).toEqual(["Speech to text", "Vision", "later"]);
    expect(energyPerCall(undefined)).toEqual([]);
    expect(usd(0.1875)).toBe("$0.19");
    expect(usd(0)).toBe("$0.00");
  });
});
