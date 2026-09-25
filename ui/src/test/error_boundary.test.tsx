import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "@/components/ErrorBoundary";

function Bomb(): React.ReactElement {
  throw new Error("render blew up");
}
afterEach(cleanup);
describe("ErrorBoundary", () => {
  it("catches a render error under the app root and offers a reload, instead of a blank screen mid-call", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(<ErrorBoundary><Bomb /></ErrorBoundary>);
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText(/Patient data stays on the vehicle server/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reload display" })).toBeTruthy();
    spy.mockRestore();
  });
  it("renders children normally when nothing throws", () => {
    render(<ErrorBoundary><p>Fine</p></ErrorBoundary>);
    expect(screen.getByText("Fine")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
