// Which category a fact belongs to, for its color and glyph (as Health colors Heart, Activity, Medications). The
// category is identity only; status is always a separate badge, icon and word.
export type Cat = "attention" | "time" | "heart" | "neuro" | "ed" | "check" | "meds" | "patient" | "speech";

export function catOf(key: string): Cat {
  if (key.startsWith("meds.") || key === "allergies") return "meds";
  if (key.startsWith("vitals.")) return "heart";
  if (key.startsWith("exam.") || key.startsWith("stroke.") || key.startsWith("symptom.") || key.startsWith("ecg.") || key.startsWith("@")) return "neuro";
  if (key.startsWith("transport.")) return "ed";
  if (key.startsWith("scene.")) return "time";
  if (key.startsWith("patient.") || key === "complaint.chief" || key === "code_status") return "patient";
  return "attention";
}

/** The category of each patient-picture group (lib/selectors GROUPS). */
export const GROUP_CAT: Record<string, Cat> = {
  Patient: "patient", History: "neuro", Vitals: "heart", Exam: "neuro", "Meds & allergies": "meds", Transport: "ed", Scene: "time", Other: "attention",
};
