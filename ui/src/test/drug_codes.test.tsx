// A medication shows the code it was matched to on the box, and the brand said when it differs from the generic.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { codedTerms, DrugCodes } from "@/components/DrugCodes";

const RX = "http://www.nlm.nih.gov/research/umls/rxnorm";
const f = (normalized: unknown[]) => ({ provenance: { normalized } }) as never;

describe("drug codes", () => {
  afterEach(cleanup);
  it("shows RxNorm with the brand that was said, and nothing for a destination match or an uncoded name", () => {
    expect(codedTerms(f([
      { said: "Eliquis", value: "apixaban", system: RX, code: "1364430", method: "exact" },
      { said: "Regional", value: "Regional Medical Center", system: "county-facility", code: "RSJ", method: "exact" },
      { said: "zzz", value: "zzz", system: null, code: null, method: "none" },
    ]))).toEqual([{ system: "RxNorm", code: "1364430", value: "apixaban", said: "Eliquis" }]);
    render(<DrugCodes f={f([{ said: "Eliquis", value: "apixaban", system: RX, code: "1364430", method: "exact" }])} />);
    expect(screen.getByText("RxNorm 1364430")).toBeTruthy();
    expect(screen.getByText(/said “Eliquis”/)).toBeTruthy();
  });
  it("does not repeat a name said as its generic, and names each drug of a list", () => {
    render(<DrugCodes f={f([
      { said: "metoprolol", value: "metoprolol", system: RX, code: "6918", method: "exact" },
      { said: "aspirin", value: "aspirin", system: RX, code: "1191", method: "exact" },
    ])} />);
    expect(screen.getByText("RxNorm 6918")).toBeTruthy();
    expect(screen.getByText("metoprolol")).toBeTruthy();
    expect(screen.queryByText(/said/)).toBeNull();
  });
  it("renders nothing for a fact with no codes", () => {
    const { container } = render(<DrugCodes f={f([])} />);
    expect(container.textContent).toBe("");
  });
});
