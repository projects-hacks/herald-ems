import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProtocolSearch } from "@/features/protocols/ProtocolSearch";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Sidebar } from "@/layout/Sidebar";
import { useHerald } from "@/lib/store";
import type { ProtocolAnswer, ProtocolPassage } from "@/lib/types";

vi.mock("@/lib/contract", () => ({ useContract: () => ({ keys: {}, relayTiers: {}, changeRules: {} }) }));

const passage = (over: Partial<ProtocolPassage> = {}): ProtocolPassage => ({
  doc: "700-A13", title: "Stroke", section: "3.2", heading: "3.2 Destination", page: 2,
  text: "3.2 Destination\nG.F.A.S.T. 4/4: Comprehensive Stroke Center.", parents: ["Stroke", "3 Procedure"],
  score: 0.9, effective: "January 1, 2026", text_layer_uncertain: false, ...over,
});
const answer = (over: Partial<ProtocolAnswer> = {}): ProtocolAnswer =>
  ({ query: "stroke", answerable: true, reranked: true, chosen: 1, results: [passage()], ...over });
const reply = (status: number, body: unknown) => vi.fn(async (_url: string) => new Response(JSON.stringify(body), { status }));

describe("ProtocolSearch", () => {
  beforeEach(() => useHerald.setState({ source: "live", snapshot: null }));
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("runs the host's query and quotes the county passage with its citation", async () => {
    const fetch = reply(200, answer());
    vi.stubGlobal("fetch", fetch);
    render(<ProtocolSearch open query="open the stroke protocol" onClose={() => {}} />);
    expect(await screen.findByText("700-A13 §3.2, page 2, effective January 1, 2026")).toBeTruthy();
    expect(screen.getByText(/G\.F\.A\.S\.T\. 4\/4: Comprehensive Stroke Center\./)).toBeTruthy();
    expect(String(fetch.mock.calls[0][0])).toBe("/api/protocols/search?q=open+the+stroke+protocol&k=5");
  });

  it("says when the county documents don't cover the question, and still lists the closest passages", async () => {
    vi.stubGlobal("fetch", reply(200, answer({ answerable: false })));
    render(<ProtocolSearch open query="helicopter fuel" onClose={() => {}} />);
    expect(await screen.findByText(/The county documents don't cover this/)).toBeTruthy();
    expect(screen.getByText("3.2 Destination")).toBeTruthy();
  });

  it("offers the printed page when the text layer is uncertain", async () => {
    vi.stubGlobal("fetch", reply(200, answer({ results: [passage({ doc: "602", page: 7, text_layer_uncertain: true })] })));
    render(<ProtocolSearch open query="table b" onClose={() => {}} />);
    const link = await screen.findByRole("link", { name: "View the printed page" });
    expect(link.getAttribute("href")).toBe("/api/protocols/602/page/7");
  });

  it.each([
    [404, { detail: "protocol lookup is off" }, "Protocol lookup is off on this vehicle."],
    [503, { detail: { ready: false, building: true, error: null } }, "The county documents are still loading. Try again in a moment."],
    [500, {}, "The Herald server didn't answer. Try again."],
  ])("shows the %i state in words", async (status, body, copy) => {
    vi.stubGlobal("fetch", reply(status, body));
    render(<ProtocolSearch open query="stroke" onClose={() => {}} />);
    expect((await screen.findByRole("alert")).textContent).toBe(copy);
  });

  it("searches what the medic types", async () => {
    const fetch = reply(200, answer());
    vi.stubGlobal("fetch", fetch);
    render(<ProtocolSearch open onClose={() => {}} />);
    expect(fetch).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Search the county protocols"), { target: { value: "sepsis" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("3.2 Destination")).toBeTruthy();
    expect(String(fetch.mock.calls[0][0])).toContain("q=sepsis");
  });

  it("is off in replay", () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    useHerald.setState({ source: "fixture" });
    render(<ProtocolSearch open query="stroke" onClose={() => {}} />);
    expect(screen.getByText("Replay: protocol search needs the live server.")).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe("Sidebar protocols entry", () => {
  afterEach(cleanup);
  it("opens the county protocol search", () => {
    useHerald.setState({ source: "live", snapshot: null });
    render(<TooltipProvider><Sidebar player={null} /></TooltipProvider>);
    fireEvent.click(screen.getByRole("button", { name: /Protocols/ }));
    expect(screen.getByRole("dialog", { name: "County protocols" })).toBeTruthy();
  });
});
