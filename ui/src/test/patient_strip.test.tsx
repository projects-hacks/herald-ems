import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PatientStrip } from "@/components/PatientStrip";
import type { PatientSummary } from "@/lib/types";

const patients: PatientSummary[] = [
  { id: "driver", label: "Driver", triage: "immediate", summary: "chest injury", readiness_done: 2, readiness_total: 6 },
  { id: "passenger", label: "Passenger", triage: "minimal", summary: "arm pain", readiness_done: 1, readiness_total: 6 },
];

describe("PatientStrip", () => {
  it("is absent for the unchanged single-patient screen", () => {
    const { container } = render(<PatientStrip patients={[patients[0]]} activePatient="driver" onActivate={() => {}} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows triage and switches to the tapped patient", () => {
    const onActivate = vi.fn();
    render(<PatientStrip patients={patients} activePatient="driver" onActivate={onActivate} />);
    expect(screen.getByText("immediate")).toBeTruthy();
    expect(screen.getByText("minimal")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Passenger/ }));
    expect(onActivate).toHaveBeenCalledWith("passenger");
  });
});
