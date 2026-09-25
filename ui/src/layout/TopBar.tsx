// The top bar of every page (UX_PLAN P3, read in one glance): who the patient is and the incident on the left; on the
// right, how many things wait on the medic, whether the pre-alert is ready, and the time. The two chips jump to the
// overview, so nothing is missed while another page is open (H7).
import { CircleCheck, CircleDashed, Inbox, OctagonAlert } from "lucide-react";
import { useAttention } from "@/hooks/useAttention";
import { useNow } from "@/hooks/useNow";
import { clockSeconds, clockTime, hhmm, hhmmss, shortId } from "@/lib/format";
import { useHerald } from "@/lib/store";
import { cn } from "@/lib/utils";
import { Badge, TINT } from "@/components/kit";
import { PatientRoster } from "@/components/PatientRoster";

function Chip({ tone, onClick, label, children }: { tone: "ok" | "medium" | "high" | "neutral"; onClick: () => void; label: string; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} aria-label={label}
      className={cn("hit inline-flex h-9 items-center gap-2 rounded-full px-3.5 text-meta font-semibold transition-[filter] hover:brightness-110", TINT[tone])}>
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
  const now = useNow();
  const [who, complaint] = (s?.summary ?? "").split(" · ");
  const scene = s?.clocks.find((c) => c.id === "scene");
  const r = s?.readiness[0];
  const goOverview = (hash?: string) => {
    setUi({ page: "overview" });
    if (hash) requestAnimationFrame(() => document.getElementById(hash)?.focus());
  };
  const meta = [
    s?.incident.dispatch ? `Dispatch: ${s.incident.dispatch}` : null,
    s ? `Incident ${shortId(s.incident.id)} · started ${hhmm(s.incident.started)}` : null,
    scene ? `On scene ${hhmmss(clockSeconds(scene, at, now))}` : null,
  ].filter(Boolean);
  return (
    <header className="sticky top-0 z-10 flex min-h-16 shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b border-border-subtle bg-canvas/85 px-6 py-2.5 backdrop-blur-md">
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-center gap-2.5">
          <h1 className="truncate text-hero font-semibold tracking-display">
            {s ? <>{who || "Patient"}<span className="px-2 font-normal text-text-muted">·</span>{complaint ? complaint[0].toUpperCase() + complaint.slice(1) : "Not described yet"}</> : "Waiting for the first capture"}
          </h1>
          {replay && <Badge tone="accent" variant="solid" className="text-[0.6875rem] tracking-wide">REPLAY</Badge>}
          {explain && <Badge tone="accent">Explain mode</Badge>}
        </div>
        <p className="num truncate text-meta text-text-muted">{meta.join("  ·  ") || "—"}</p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {a && (a.count > 0
          ? <Chip tone={a.urgent.length ? "high" : "medium"} onClick={() => goOverview("needs-attention")} label={`${a.count} need your attention. Go to the list.`}>
              {a.urgent.length ? <OctagonAlert size={15} className="flash-high" aria-hidden /> : <Inbox size={15} aria-hidden />}
              <span className="num">{a.count}</span> need attention
            </Chip>
          : <Chip tone="neutral" onClick={() => goOverview()} label="Nothing to confirm"><CircleCheck size={15} aria-hidden />Nothing to confirm</Chip>)}
        {r && (r.ready
          ? <Chip tone="ok" onClick={() => goOverview("prealert")} label={`${r.label} ready, ${r.done} of ${r.total}`}><CircleCheck size={15} aria-hidden />{r.label} ready</Chip>
          : <Chip tone="neutral" onClick={() => goOverview("prealert")} label={`${r.label}: ${r.done} of ${r.total}`}><CircleDashed size={15} aria-hidden />{r.label} <span className="num">{r.done}/{r.total}</span></Chip>)}
        <span className="num ml-2 font-mono text-body font-semibold text-text-secondary" aria-label="Time">{clockTime(now)}</span>
      </div>
      <PatientRoster />
    </header>
  );
}
