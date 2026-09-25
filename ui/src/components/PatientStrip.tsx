import type { PatientSummary, TriageCategory } from "@/lib/types";
import { cn } from "@/lib/utils";

const TRIAGE_STYLE: Record<TriageCategory | "unknown", string> = {
  immediate: "bg-high-fill text-high-on-fill",
  delayed: "bg-medium-fill text-medium-on-fill border border-medium-fill-border",
  minimal: "bg-ok-fill text-ok-on-fill",
  expectant: "bg-accent-fill text-on-accent-fill",
  dead: "bg-text-secondary text-bg",
  unknown: "bg-surface-3 text-text-secondary",
};

/** Standalone S5 component for Tushar to place in the NOW screen layout. */
export function PatientStrip({ patients, activePatient, onActivate, disabled = false }: {
  patients: PatientSummary[];
  activePatient: string;
  onActivate: (patientId: string) => void;
  disabled?: boolean;
}) {
  if (patients.length <= 1) return null;
  return (
    <nav aria-label="Patients" className="flex gap-2 overflow-x-auto py-1">
      {patients.map((patient) => {
        const triage = patient.triage ?? "unknown";
        const active = patient.id === activePatient;
        return (
          <button key={patient.id} type="button" aria-pressed={active} disabled={disabled || active}
            onClick={() => onActivate(patient.id)}
            className={cn("hit flex min-h-12 min-w-40 shrink-0 items-center gap-2 rounded-[var(--radius-control)] border bg-surface-1 px-3 py-2 text-left",
              active ? "border-accent-fill ring-2 ring-accent-fill/30" : "border-border-subtle",
              "disabled:cursor-default disabled:opacity-100")}>
            <span className={cn("rounded-full px-2 py-0.5 text-meta font-semibold uppercase", TRIAGE_STYLE[triage])}>
              {triage}
            </span>
            <span className="min-w-0">
              <span className="block truncate text-button font-semibold text-text-primary">{patient.label}</span>
              <span className="block text-meta text-text-muted">{patient.readiness_done}/{patient.readiness_total} ready</span>
            </span>
          </button>
        );
      })}
    </nav>
  );
}
