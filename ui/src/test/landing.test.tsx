// The public landing page (landing/index.html, the homepage): it renders without a backend, never asks for a device,
// links to the app and the recorded stroke call, shows its content at rest (no section waits for a scroll to become
// visible), and every extraction figure it quotes is the one in README.md's measured results.
import { readFileSync } from "node:fs";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { COMPARISON, LINKS, SHOTS, STATS } from "@/features/landing/content";
import { LandingApp } from "@/screens/LandingApp";

const readme = readFileSync("../README.md", "utf8");
const css = readFileSync("src/features/landing/landing.css", "utf8");

describe("landing page", () => {
  beforeEach(() => {
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn() } });
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it("renders the headline and every section, and opens no device", () => {
    render(<LandingApp />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("before the doors open");
    for (const id of ["why", "journey", "features", "handover", "results", "trust", "edge"]) {
      expect(document.getElementById(id)).not.toBeNull();
    }
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
  });

  it("links Try now and Open Herald to the app, and Watch the demo to the recorded call", () => {
    expect(LINKS.app).toBe("/app/");
    expect(LINKS.replay).toBe("/app/?fixture=stroke_demo");
    render(<LandingApp />);
    const links = screen.getAllByRole("link");
    const hrefOf = (name: RegExp) => links.filter((a) => name.test(a.textContent ?? "")).map((a) => a.getAttribute("href"));
    expect(hrefOf(/Try now/)).toContain("/app/");
    expect(hrefOf(/Watch the demo/)).toContain("/app/?fixture=stroke_demo");
    expect(hrefOf(/Open Herald/)).toEqual(["/app/"]);
    expect(hrefOf(/Source/)[0]).toBe(LINKS.source);
    // the two hero buttons sit side by side, primary first
    const hero = document.getElementById("top")!;
    const heroLinks = Array.from(hero.querySelectorAll("a")).map((a) => a.textContent?.trim());
    expect(heroLinks.slice(0, 2)).toEqual(["Try now", "Watch the demo"]);
  });

  it("is visible at rest: nothing is hidden waiting for a scroll or an animation", () => {
    render(<LandingApp />);
    expect(document.querySelectorAll(".lp-reveal").length).toBeGreaterThan(0);
    // no reveal element is armed in a static render, and the reveal (and the hero's entrance) never touch opacity
    expect(document.querySelectorAll(".is-armed")).toHaveLength(0);
    expect(css).not.toMatch(/\.lp-reveal[^{]*\{[^}]*opacity/);
    expect(css).not.toMatch(/@keyframes lp-enter[^}]*opacity/);
    for (const shot of Object.values(SHOTS)) {
      const imgs = screen.getAllByAltText(shot.alt);
      for (const img of imgs) expect(img.getAttribute("src")).toBe(shot.src);
    }
  });

  it("never mentions synthetic data, and the footer is only the hackathon line", () => {
    render(<LandingApp />);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/synthetic/i);
    expect(text).not.toMatch(/not a medical device/i);
    expect(text).not.toMatch(/honest limits/i);
    expect(screen.getByRole("contentinfo").textContent).toContain("Hackathon prototype · HP Edge AI SJSU Hack, September 2026");
    expect(text).toContain("Herald never recommends treatment");
    expect(text).toContain("99.4%");
  });

  it("compares the prompted 30B model with our fine-tuned 4B model exactly as README.md reports them", () => {
    expect(COMPARISON).toHaveLength(2);
    for (const c of COMPARISON) expect(readme).toContain(c.f1.toFixed(3));
    expect(COMPARISON.find((c) => c.ours)?.f1).toBe(0.95);
    expect(COMPARISON.find((c) => !c.ours)?.f1).toBe(0.661);
    expect(readme).toContain("0 duplicates, 0 lost across 20 seeds with 50% loss");
    // 99.4% = 160 of the 161 self-confirmed medic facts (README: "161 (57%) auto-confirm, 1 of them wrong")
    expect(readme).toContain("161 (57%) auto-confirm, 1 of them wrong");
    expect(((160 / 161) * 100).toFixed(1)).toBe("99.4");
    expect(STATS.map((s) => s.value)).toContain("0");
    render(<LandingApp />);
    const results = document.getElementById("results")!;
    expect(results.textContent).toContain("0.661");
    expect(results.textContent).toContain("0.950");
    expect(results.textContent).toContain("Qwen3-VL-30B-A3B");
    expect(results.textContent).toContain("Whisper large-v3-turbo");
  });
});
