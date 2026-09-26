// The terminology codes a drug or allergy was matched to on the box (herald/terminology: RxNorm for drugs, ICD-10-CM
// for an allergy class), with the word said when it differs from the generic name: "RxNorm 1364430 · said “Eliquis”".
// Shown where the medic reads or confirms a medication, so a brand name visibly lands on the right generic.
import { Pill } from "lucide-react";
import type { FactView } from "@/lib/types";
import { cn } from "@/lib/utils";

const SYSTEMS: Record<string, string> = {
  "http://www.nlm.nih.gov/research/umls/rxnorm": "RxNorm",
  "http://hl7.org/fhir/sid/icd-10-cm": "ICD-10-CM",
};

export interface CodedTerm { system: string; code: string; value: string; said: string | null }

/** Every coded item of a fact, in the order said; a destination match or an uncoded name is not a code. */
export function codedTerms(f: Pick<FactView, "provenance">): CodedTerm[] {
  return (f.provenance?.normalized ?? []).flatMap((n) => {
    const system = n.system ? SYSTEMS[n.system] : undefined;
    if (!system || !n.code) return [];
    const value = String(n.value ?? "");
    const said = n.said && n.said.trim().toLowerCase() !== value.trim().toLowerCase() ? n.said.trim() : null;
    return [{ system, code: String(n.code), value, said }];
  });
}

export function DrugCodes({ f, className }: { f: Pick<FactView, "provenance">; className?: string }) {
  const terms = codedTerms(f);
  if (!terms.length) return null;
  return (
    <span className={cn("flex flex-wrap items-center gap-1.5", className)}>
      {terms.map((t) => (
        <span key={`${t.system}:${t.code}:${t.said ?? ""}`}
          className="inline-flex items-center gap-1 rounded-md border border-border-subtle bg-surface-2 px-1.5 py-0.5 text-meta font-normal text-text-secondary"
          title={`${t.value}: ${t.system} ${t.code}${t.said ? `, said “${t.said}”` : ""}`}>
          <Pill size={12} aria-hidden className="text-text-muted" />
          {terms.length > 1 && <span className="text-text-primary">{t.value}</span>}
          <span className="num">{t.system} {t.code}</span>
          {t.said && <span>· said “{t.said}”</span>}
        </span>
      ))}
    </span>
  );
}
