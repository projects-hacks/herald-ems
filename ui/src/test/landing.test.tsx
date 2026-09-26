// The public landing page (landing/index.html): it renders without a backend, never asks for a device, links to the
// recorded stroke call, and every extractor figure it quotes is the one in README.md's measured results.
import { readFileSync } from "node:fs";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EXTRACTORS, LINKS, STATS } from "@/features/landing/content";
import { LandingApp } from "@/screens/LandingApp";

const readme = readFileSync("../README.md", "utf8");

describe("landing page", () => {
  beforeEach(() => {
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn() } });
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it("renders the headline, every section and the replay link, and opens no device", () => {
    render(<LandingApp />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("before the doors open");
    for (const id of ["how", "features", "trust", "results", "edge"]) expect(document.getElementById(id)).not.toBeNull();
    const replay = screen.getAllByRole("link").filter((a) => a.getAttribute("href") === LINKS.replay);
    expect(replay.length).toBeGreaterThan(0);
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
  });

  it("quotes each extractor's F1 exactly as README.md reports it", () => {
    for (const e of EXTRACTORS) expect(readme).toContain(e.f1.toFixed(3));
    expect(readme).toContain("0 duplicates, 0 lost across 20 seeds with 50% loss");
    expect(STATS.map((s) => s.value)).toContain("0");
  });

  it("shows the same figures as a table, and a bar's detail on hover", () => {
    render(<LandingApp />);
    const results = document.getElementById("results")!;
    const live = EXTRACTORS.find((e) => e.live)!;
    fireEvent.mouseEnter(within(results).getByText(live.name).closest("button")!);
    expect(within(results).getByRole("tooltip").textContent).toContain(live.latency);
    fireEvent.click(within(results).getByRole("button", { name: /table/i }));
    const rows = within(results).getAllByRole("row");
    expect(rows).toHaveLength(EXTRACTORS.length + 1);
    expect(within(results).getByRole("table").textContent).toContain(live.f1.toFixed(3));
  });
});
