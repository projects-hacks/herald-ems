// The top bar of every page (UX_PLAN P3, read in one glance), as an iOS large-title header: the patient's avatar and
// complaint as the title, the patient and incident details under it; on the right, how many things wait on the
// medic, whether the pre-alert is ready, and the time. The two capsules jump to the summary, so nothing is missed
// while another page is open (H7).
import { CircleCheck, CircleDashed, Inbox, OctagonAlert } from "lucide-react";
import { useAttention } from "@/hooks/useAttention";
import { useNow } from "@/hooks/useNow";
import { clockSeconds, clockTime, hhmm, hhmmss, shortId } from "@/lib/format";
import { useHerald, type IncidentPhase } from "@/lib/store";
import { cn } from "@/lib/utils";
import { Badge, TINT } from "@/components/kit";
import { PatientRoster } from "@/components/PatientRoster";

const PHASES: { id: IncidentPhase; label: string }[] = [
  { id: "scene", label: "Scene" }, { id: "transport", label: "Transport" }, { id: "handoff", label: "Handoff" },
];

function Capsule({ tone, onClick, label, children }: { tone: "ok" | "medium" | "high" | "neutral"; onClick: () => void; label: string; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} aria-label={label}
      className={cn("hit inline-flex h-9 items-center gap-1.5 rounded-full px-3.5 text-meta font-semibold transition-[filter] hover:brightness-110", TINT[tone])}>
      {children}
    </button>
  );
}

export function TopBar() {
  const s = useHerald((st) => st.snapshot);
  const at = useHerald((st) => st.lastStateAt);
  const replay = useHerald((st) => st.source === "fixture");
  const explain = useHerald((st) => st.ui.mode === "explain");
  const setUi = useHerald((st) => st.setUi);
  const a = useAttention();
  const phase = useHerald((st) => st.ui.incidentPhase);
  const now = useNow();
  const [who, complaint] = (s?.summary ?? "").split(" · ");
  const scene = s?.clocks.find((c) => c.id === "scene");
  const r = s?.readiness[0];
  const demographicsComplete = s?.facts["patient.age"]?.status === "confirmed" && s?.facts["patient.sex"]?.status === "confirmed";
  const name = s?.facts["patient.name"];
  const identifier = s?.facts["patient.identifier"];
  const goSummary = (id?: string) => {
    setUi({ page: "overview" });
    if (id) requestAnimationFrame(() => document.getElementById(id)?.focus());
  };
  // the avatar shows age and sex; the line under the title carries the incident
  const meta = [
    s?.incident.dispatch ? `Dispatch: ${s.incident.dispatch}` : null,
    s && !demographicsComplete ? "Patient demographics incomplete" : null,
    scene ? `call elapsed ${hhmmss(clockSeconds(scene, at, now))}` : null,
    s ? `started ${hhmm(s.incident.started)} · incident ${shortId(s.incident.id)}` : null,
  ].filter(Boolean);
  return (
    <header className="sticky top-0 z-10 flex min-h-[4.75rem] shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b border-border-subtle bg-bg/80 px-6 py-3 backdrop-blur-xl">
      <span className="rounded-num grid size-12 shrink-0 place-items-center rounded-full bg-gradient-to-b from-[#A1A1A6] to-[#7C7C80] text-[0.9375rem] text-white" aria-hidden>
        {who ? who.replace(/\s+/g, "") : "—"}
      </span>
      <div className="min-w-0 flex-1">
        <p className="break-words text-body font-semibold text-text-secondary">
          {name?.status === "confirmed" ? String(name.value) : "Patient identity not confirmed"}
          {identifier?.status === "confirmed" ? ` · ID ${String(identifier.value)}` : " · Identifier not confirmed"}
        </p>
        <div className="flex min-w-0 items-center gap-2">
          <h1 className="truncate text-large-title font-bold tracking-display">
            {who && <span className="sr-only">{who}, </span>}
            {s ? (complaint ? complaint[0].toUpperCase() + complaint.slice(1) : "Not described yet") : "Waiting for the first capture"}
          </h1>
          {replay && <Badge tone="accent" variant="solid" className="rounded-[6px] px-1.5 text-[0.6875rem] tracking-wide">REPLAY</Badge>}
          {explain && <Badge tone="accent">Explain mode</Badge>}
        </div>
        <p className="num truncate text-body text-text-muted">{meta.join("  ·  ") || "—"}</p>
      </div>
      <div className="flex max-w-full flex-wrap items-center gap-2">
        <div role="group" aria-label="Workspace phase (this screen only)" className="flex rounded-full bg-surface-1 p-1">
          {PHASES.map((item) => <button key={item.id} type="button" aria-pressed={phase === item.id}
            onClick={() => setUi({ incidentPhase: item.id, ...(item.id === "handoff" ? { page: "handoff" as const } : {}) })}
            className={cn("h-12 rounded-full px-3 text-meta font-semibold", phase === item.id ? "bg-accent-fill text-on-accent-fill" : "text-text-muted hover:text-text-primary")}>{item.label}</button>)}
        </div>
        {a && (a.count > 0
          ? <Capsule tone={a.urgent.length ? "high" : "medium"} onClick={() => goSummary("needs-attention")} label={`${a.count} need your attention. Go to the list.`}>
              {a.urgent.length ? <OctagonAlert size={15} className="flash-high" aria-hidden /> : <Inbox size={15} aria-hidden />}
              <span className="num">{a.count}</span> need attention
            </Capsule>
          : <Capsule tone="neutral" onClick={() => goSummary()} label="Nothing to confirm"><CircleCheck size={15} aria-hidden />Nothing to confirm</Capsule>)}
        {r && (r.ready
          ? <Capsule tone="ok" onClick={() => goSummary("prealert")} label={`${r.label} ready, ${r.done} of ${r.total}`}><CircleCheck size={15} aria-hidden />{r.label} ready</Capsule>
          : <Capsule tone="neutral" onClick={() => goSummary("prealert")} label={`${r.label}: ${r.done} of ${r.total} items captured`}><CircleDashed size={15} aria-hidden />{r.label} <span className="num">{r.done}/{r.total}</span> captured</Capsule>)}
        <span className="rounded-num ml-2 text-[1.0625rem] text-text-secondary" aria-label="Time">{clockTime(now)}</span>
      </div>
      <PatientRoster />
    </header>
  );
}
