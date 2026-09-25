import { describe, expect, it } from "vitest";
import { manualValue } from "@/lib/manual";

describe("explicit manual values", () => {
  const sbp = { label: "Systolic BP", type: "int", range: [0, 300] as [number, number], unit: "mmHg" };
  it("never turns blank input into a zero reading", () => {
    expect(() => manualValue(" ", sbp)).toThrow();
    expect(manualValue("0", sbp)).toBe(0);
  });
  it("rejects implausible, fractional and nonfinite integer readings", () => {
    for (const input of ["301", "-1", "120.5", "Infinity", "NaN"]) expect(() => manualValue(input, sbp)).toThrow();
    expect(manualValue("138", sbp)).toBe(138);
  });
  it("requires explicit absence and yes/no values", () => {
    expect(manualValue("[]", { type: "list", label: "Allergies" })).toEqual([]);
    expect(() => manualValue(", ,", { type: "list", label: "Allergies" })).toThrow();
    expect(() => manualValue("unknown", { type: "bool", label: "Oxygen" })).toThrow();
    expect(manualValue("false", { type: "bool", label: "Oxygen" })).toBe(false);
  });
});
