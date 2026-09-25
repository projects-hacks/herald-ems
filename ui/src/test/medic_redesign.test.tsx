import { readFileSync } from "node:fs";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CabinApp } from "@/features/cabin/CabinApp";
import { CareSummary, PatientSafetySummary } from "@/features/cabin/CareSummary";
import { ProtocolLibrary } from "@/features/cabin/ProtocolLibrary";
import { initialUi, useHerald } from "@/lib/store";
import type { Snapshot } from "@/lib/types";

const snapshot: Snapshot = JSON.parse(readFileSync("src/test/fixtures/live_every_call.json", "utf8"));
beforeEach(() => {
  localStorage.clear();
  useHerald.setState({ snapshot, source: "live", stale: false, conn: "open", ui: initialUi("") });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("medic workspace navigation", () => {
  it("is one screen: the record opens from the header, capture stays available, and Back returns to Now", () => {
    render(<CabinApp />);
    expect(screen.queryByRole("navigation", { name: "Care workspace" })).toBeNull();   // no page sidebar
    fireEvent.click(screen.getByRole("button", { name: "Record" }));
    expect(screen.getByRole("heading", { name: "Patient", level: 1 })).toBeTruthy();
    expect(screen.getByRole("tablist", { name: "Record views" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Start listening" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Back to now" }));
    expect(screen.getByRole("region", { name: "How the patient is moving" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Protocols" }));
    expect(screen.getByRole("dialog", { name: "County protocols" })).toBeTruthy();
  });
  it("switches between server-provided checklists without inventing completion", () => {
    render(<CareSummary onReview={() => {}} />);
    const second = snapshot.readiness[1];
    fireEvent.change(screen.getByLabelText("Pre-alert checklist"), { target: { value: second.id } });
    expect(screen.getByLabelText("Pre-alert checklist").textContent).toContain(second.label);
    const list = screen.getByRole("list");
    expect(within(list).getAllByRole("listitem")).toHaveLength(second.items.length);
    expect(within(list).getAllByText("Captured")).toHaveLength(second.items.filter((item) => item.state === "done").length);
  });
  it("does not show unverified allergy values as established patient information", () => {
    const allergy = snapshot.facts.allergies;
    useHerald.setState({ snapshot: { ...snapshot, facts: { allergies: { ...allergy, value: ["unverified-allergen"], status: "unconfirmed" } } } });
    render(<PatientSafetySummary onReview={() => {}} />);
    expect(screen.getByText("Needs verification")).toBeTruthy();
    expect(screen.queryByText("unverified-allergen")).toBeNull();
  });
  it("warns the medic when an unfinished call was restored", () => {
    useHerald.setState({ snapshot: { ...snapshot, restored: true } });
    render(<CabinApp />);
    expect(screen.getByText(/Unfinished call restored/)).toBeTruthy();
  });
});

describe("local protocol library", () => {
  const passage = { doc: "policy-501", title: "Radio report policy", section: "2", heading: "Communication", page: 3, text: "Original county passage for this test.", effective: "2026-01-01", text_layer_uncertain: true };
  const submit = () => {
    fireEvent.change(screen.getByLabelText("Search county protocols"), { target: { value: "radio report" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
  };
  it("renders the original passage with citation and uncertain-text notice", async () => {
    const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ query: "radio report", answerable: false, results: [passage] }) });
    vi.stubGlobal("fetch", fetcher);
    render(<ProtocolLibrary />); submit();
    expect(await screen.findByText(passage.text)).toBeTruthy();
    expect(screen.getByText(/could not establish an answer/)).toBeTruthy();
    expect(screen.getByText(/Text extraction is uncertain/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /Radio report policy/ }).getAttribute("href")).toBe("/api/protocols/policy-501/page/3");
    expect(fetcher.mock.calls[0][0]).toBe("/api/protocols/search?q=radio%20report&k=5");
  });
  it("shows actionable availability errors and allows retry", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503 }));
    render(<ProtocolLibrary />); submit();
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "The local protocol library is preparing. Try again shortly.");
    expect((screen.getByRole("button", { name: "Search" }) as HTMLButtonElement).disabled).toBe(false);
  });
  it("never searches the live service from replay mode", () => {
    const fetcher = vi.fn(); vi.stubGlobal("fetch", fetcher);
    useHerald.setState({ source: "fixture" });
    render(<ProtocolLibrary />); submit();
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("discards a pending response after the county changes", async () => {
    let resolve!: (value: unknown) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise((done) => { resolve = done; })));
    render(<ProtocolLibrary />); submit();
    act(() => useHerald.setState({ snapshot: { ...snapshot, county: { id: "another", name: "Another county" } } }));
    await act(async () => { resolve({ ok: true, json: async () => ({ query: "radio report", results: [passage] }) }); });
    await waitFor(() => expect(screen.queryByText(passage.text)).toBeNull());
  });
});
