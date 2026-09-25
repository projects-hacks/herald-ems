import { describe, expect, it } from "vitest";
import { cn } from "@/lib/utils";

describe("cn", () => {
  it("keeps a Herald type size next to a color (regression: sizes were dropped as if they were colors)", () => {
    expect(cn("text-kpi", "text-ok-fg")).toBe("text-kpi text-ok-fg");
    expect(cn("text-critical font-semibold", "text-text-muted")).toBe("text-critical font-semibold text-text-muted");
  });
  it("still lets a later size replace an earlier one", () => {
    expect(cn("text-body", "text-meta")).toBe("text-meta");
  });
});
