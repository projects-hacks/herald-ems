import {
  ArrowRight, AudioLines, BrainCircuit, Check, CircleAlert, Hospital, Pause, Play, RotateCcw, ShieldCheck,
  SkipForward, Sparkles, Stethoscope, Wifi, WifiOff,
} from "lucide-react";
import { useAttention } from "@/hooks/useAttention";
import { useNow } from "@/hooks/useNow";
import { elapsedAgo } from "@/lib/clock";
import { clockSeconds, factValue, formatValue, hhmm } from "@/lib/format";
import { useHerald } from "@/lib/store";
import { activeSync, allFacts } from "@/lib/selectors";
import type { FactView, Snapshot } from "@/lib/types";
import type { FixturePlayer } from "@/lib/ws";
import { cn } from "@/lib/utils";

function PlainFact({ label, fact, value }: { label: string; fact?: FactView; value?: string }) {
  return (
    <div className="flex min-h-14 items-center gap-3 border-b border-border-subtle py-2.5 last:border-0">
      <span className="size-2 shrink-0 rounded-full bg-herald-accent" aria-hidden />
      <span className="min-w-0 flex-1 text-body text-text-muted">{label}</span>
      <strong className="max-w-[62%] text-right text-body font-semibold text-text-primary">{value ?? (fact ? factValue(fact) : "Not captured yet")}</strong>
    </div>
  );
}

function Stage({ n, title, detail, state }: { n: number; title: string; detail: string; state: "done" | "active" | "waiting" }) {
  return (
    <div className={cn("flex min-w-0 items-center gap-3 rounded-[18px] px-4 py-3",
      state === "active" ? "bg-accent-tint text-herald-accent" : "bg-surface-1 text-text-secondary")}>
      <span className={cn("grid size-8 shrink-0 place-items-center rounded-full text-meta font-bold",
        state === "done" ? "bg-ok-fill text-ok-on-fill" : state === "active" ? "bg-accent-fill text-on-accent-fill" : "bg-surface-2 text-text-muted")}>
        {state === "done" ? <Check size={16} strokeWidth={3} /> : n}
      </span>
      <span className="min-w-0"><strong className="block truncate text-body">{title}</strong><span className="block truncate text-meta text-text-muted">{detail}</span></span>
    </div>
  );
}

function ReplayControls({ player }: { player: FixturePlayer }) {
  const f = useHerald((s) => s.fixture);
  if (!f) return null;
  const button = "grid size-10 place-items-center rounded-full bg-surface-2 text-text-secondary hover:bg-accent-tint hover:text-herald-accent";
  return (
    <div className="flex items-center gap-2 rounded-full border border-border-subtle bg-surface-1 p-1.5 pl-3 shadow-[var(--shadow-1)]">
      <span className="num mr-1 text-meta font-semibold text-text-muted">Scene {f.index}/{f.total}</span>
      <button type="button" className={button} onClick={() => f.playing ? player.pause() : player.play()} aria-label={f.playing ? "Pause demo" : "Play demo"}>
        {f.playing ? <Pause size={17} /> : <Play size={17} />}
      </button>
      <button type="button" className={button} onClick={() => player.step()} aria-label="Next demo moment"><SkipForward size={17} /></button>
      <button type="button" className={button} onClick={() => player.restart()} aria-label="Restart demo"><RotateCcw size={17} /></button>
    </div>
  );
}

function cueFor(s: Snapshot | null, attentionCount: number, hasConflict: boolean): string {
  if (!s || s.transcripts.length === 0) return "Start the replay. Herald listens in the background while the medic works normally.";
  if (hasConflict) return "Herald caught two different allergy answers. It keeps the new answer off the ER report until a human chooses.";
  if (s.alerts.some((a) => a.type === "news2_rise")) return "The vital signs changed. Herald recalculated the published score and surfaced the change without giving treatment advice.";
  if (s.readiness.some((r) => r.ready)) return "The hospital pre-alert is complete. Only confirmed essentials are sent; the full conversation stays in the ambulance.";
  if (attentionCount > 0) return "Herald extracted the facts, but anything uncertain waits for a medic's tap before it can leave the vehicle.";
  return "As the medic speaks, Herald turns the conversation into a structured patient picture and closes missing-information gaps.";
}

export function PresentationApp({ player }: { player: FixturePlayer | null }) {
  const s = useHerald((st) => st.snapshot);
  const setUi = useHerald((st) => st.setUi);
  const source = useHerald((st) => st.source);
  const a = useAttention();
  const latest = s?.transcripts.at(-1);
  const latestFacts = latest ? [...latest.trace.rules.facts, ...(latest.trace.model.facts ?? [])] : [];
  const readiness = s?.readiness[0];
  const conflict = a?.choose[0];
  const hasConflict = conflict?.type === "contradiction";
  const sent = s ? Object.values(activeSync(s)).filter((v) => v === "sent").length : 0;
  const queued = s ? Object.values(activeSync(s)).filter((v) => v === "queued").length : 0;
  const held = s ? allFacts(s).filter((f) => f.status === "unconfirmed").length : 0;
  const attentionCount = a?.count ?? 0;
  const facts = s?.facts ?? {};
  const now = useNow();
  const at = useHerald((st) => st.lastStateAt);
  const lkw = facts["stroke.lkw"];
  // "13:04 · 1 h 12 m ago", anchored on the snapshot's LKW clock exactly like the medic StatTiles (replay-safe).
  const lkwClock = s?.clocks.find((c) => c.id === "lkw");
  const stages: ("done" | "active" | "waiting")[] = [
    latest ? "done" : "active",
    s && s.counters.facts > 0 ? "done" : latest ? "active" : "waiting",
    attentionCount > 0 ? "active" : s && s.counters.facts > 0 ? "done" : "waiting",
    sent > 0 ? "done" : s?.relay.authorized ? "active" : "waiting",
  ];
  const LinkIcon = s?.relay.link === "down" ? WifiOff : Wifi;
  const modelMs = latest?.trace.model.ms;

  return (
    <div className="flex h-dvh min-h-[700px] flex-col overflow-hidden bg-canvas text-text-primary max-lg:h-auto max-lg:min-h-dvh max-lg:overflow-visible">
      <header className="flex min-h-20 shrink-0 items-center gap-4 border-b border-border-subtle bg-surface-1 px-7">
        <span className="grid size-11 place-items-center rounded-full bg-accent-fill text-on-accent-fill"><AudioLines size={21} /></span>
        <div><p className="text-critical font-bold tracking-display">Herald</p><p className="text-meta text-text-muted">Guided presentation · all AI runs on this vehicle</p></div>
        {source === "fixture" && <span className="rounded-full bg-accent-tint px-3 py-1 text-meta font-bold text-herald-accent">RECORDED DEMO</span>}
        <div className="ml-auto flex items-center gap-3">
          {player && <ReplayControls player={player} />}
          <button type="button" onClick={() => setUi({ presentationMode: false })}
            className="hit inline-flex h-11 items-center gap-2 rounded-full bg-surface-2 px-4 text-button font-semibold text-text-secondary hover:text-text-primary">
            <Stethoscope size={17} />Clinical view
          </button>
        </div>
      </header>

      <main className="mx-auto flex min-h-0 w-full max-w-[1500px] flex-1 flex-col gap-4 overflow-y-auto px-7 py-5 max-lg:overflow-visible max-lg:px-5">
        <section aria-label="How Herald works" className="grid shrink-0 grid-cols-4 gap-3 max-lg:grid-cols-2">
          <Stage n={1} title="Listen" detail="Medic speaks naturally" state={stages[0]} />
          <Stage n={2} title="Build the picture" detail="Local AI structures facts" state={stages[1]} />
          <Stage n={3} title="Human check" detail="Uncertainty waits for a tap" state={stages[2]} />
          <Stage n={4} title="Update the ER" detail="Confirmed essentials only" state={stages[3]} />
        </section>

        <div className="grid min-h-0 flex-1 grid-cols-12 gap-4 max-lg:flex max-lg:flex-col">
          <section className="card col-span-7 flex min-h-0 flex-col overflow-hidden" aria-labelledby="heard-demo">
            <div className="flex items-center gap-3 border-b border-border-subtle px-5 py-4">
              <span className="grid size-10 place-items-center rounded-full bg-accent-tint text-herald-accent"><AudioLines size={18} /></span>
              <div><h2 id="heard-demo" className="text-title font-semibold">What Herald just heard</h2><p className="text-meta text-text-muted">Speech becomes structured data on the vehicle</p></div>
              {modelMs && <span className="num ml-auto rounded-full bg-ok-tint px-3 py-1 text-meta font-semibold text-ok-fg">Processed locally in {(modelMs / 1000).toFixed(1)} s</span>}
            </div>
            <div className="px-6 py-5">
              {latest ? <>
                <p className="text-meta font-semibold text-text-muted">{latest.speaker ?? latest.captured_by} · {hhmm(latest.ts)}</p>
                <blockquote className="mt-2 text-[1.45rem] leading-8 font-medium tracking-display">“{latest.text}”</blockquote>
                <div className="mt-4 flex flex-wrap gap-2">
                  {latestFacts.length > 0 ? latestFacts.slice(0, 7).map((f) => (
                    <span key={f.id} className={cn("rounded-full px-3 py-1.5 text-meta font-semibold",
                      f.status === "unconfirmed" ? "bg-medium-tint text-medium-fg" : "bg-accent-tint text-herald-accent")}>
                      {f.label}: {formatValue(f.value)}{f.status === "unconfirmed" ? " · human check" : ""}
                    </span>
                  )) : <span className="text-body text-text-muted">Waiting for the local model…</span>}
                </div>
              </> : <p className="py-6 text-center text-critical text-text-muted">Start the replay to hear the first patient update.</p>}
            </div>
            <div className="mt-auto grid grid-cols-2 border-t border-border-subtle max-sm:grid-cols-1">
              <div className="px-5 py-4 sm:border-r sm:border-border-subtle">
                <div className="mb-2 flex items-center gap-2"><BrainCircuit size={17} className="text-herald-accent" /><h3 className="text-title font-semibold">Patient picture</h3></div>
                <PlainFact label="Patient" fact={facts["patient.age"]} value={s?.summary || undefined} />
                <PlainFact label="Last seen normal" fact={lkw} value={typeof lkw?.value === "string" && lkwClock ? `${lkw.value} · ${elapsedAgo(clockSeconds(lkwClock, at, now))}` : undefined} />
                <PlainFact label="Blood thinner" fact={facts["meds.anticoagulant"]} />
              </div>
              <div className="px-5 py-4">
                <div className="mb-2 flex items-center gap-2"><ShieldCheck size={17} className="text-ok-fg" /><h3 className="text-title font-semibold">Hospital pre-alert</h3></div>
                <div className="flex items-end gap-2"><strong className="num text-[2.25rem] leading-10 tracking-display">{readiness?.done ?? 0}</strong><span className="pb-1 text-body text-text-muted">of {readiness?.total ?? 0} essentials ready</span></div>
                <div className="mt-3 flex h-2 gap-1">{readiness?.items.map((item) => <span key={item.key} className={cn("flex-1 rounded-full", item.state === "done" ? "bg-ok-fg" : item.state === "pending" ? "bg-medium-fg" : "bg-border-control")} />)}</div>
                <p className="mt-3 text-body text-text-muted">{readiness?.ready ? "The ER has enough confirmed information for the pre-alert." : `${(readiness?.total ?? 0) - (readiness?.done ?? 0)} pieces are still missing or need confirmation.`}</p>
              </div>
            </div>
          </section>

          <div className="col-span-5 flex min-h-0 flex-col gap-4">
            <section className={cn("card p-4", hasConflict && "border-medium-fg/30")} aria-labelledby="human-demo">
              <div className="flex items-center gap-3"><span className="grid size-10 place-items-center rounded-full bg-medium-tint text-medium-fg"><CircleAlert size={19} /></span><div><h2 id="human-demo" className="text-title font-semibold">Human stays in control</h2><p className="text-meta text-text-muted">Herald never guesses when sources disagree</p></div></div>
              {hasConflict ? <div className="mt-3 rounded-[18px] bg-medium-tint p-3.5">
                <p className="font-semibold text-medium-fg">Two people gave different allergy answers</p>
                <div className="mt-2.5 grid grid-cols-2 gap-2">{conflict.facts.slice(0, 2).map((f) => <div key={f.id} className="rounded-[14px] bg-surface-1 p-2.5"><p className="text-meta text-text-muted">{f.speaker ?? f.role} said</p><p className="mt-0.5 text-critical font-semibold">{formatValue(f.value)}</p></div>)}</div>
                <p className="mt-2.5 text-body text-text-secondary">The newer answer is held inside the ambulance until the medic chooses.</p>
              </div> : attentionCount > 0 ? <p className="mt-4 rounded-[18px] bg-accent-tint p-4 text-body text-text-secondary"><strong className="text-herald-accent">{attentionCount} item{attentionCount === 1 ? "" : "s"}</strong> waiting for a medic's review. Nothing uncertain is sent automatically.</p>
              : <p className="mt-4 rounded-[18px] bg-ok-tint p-4 text-body text-ok-fg">No human checks are waiting right now.</p>}
            </section>

            <section className="card flex-1 p-4" aria-labelledby="er-demo">
              <div className="flex items-center gap-3"><span className="grid size-10 place-items-center rounded-full bg-ok-tint text-ok-fg"><Hospital size={19} /></span><div><h2 id="er-demo" className="text-title font-semibold">What the ER receives</h2><p className="text-meta text-text-muted">A tiny, prioritized update over the available link</p></div><span className="ml-auto inline-flex items-center gap-1.5 text-meta font-semibold text-text-secondary"><LinkIcon size={15} />{s?.relay.link ?? "waiting"}</span></div>
              <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                <div className="rounded-[16px] bg-ok-tint p-2.5"><strong className="num block text-kpi text-ok-fg">{sent}</strong><span className="text-meta text-text-muted">confirmed fields sent</span></div>
                <div className="rounded-[16px] bg-low-tint p-2.5"><strong className="num block text-kpi text-low-fg">{queued}</strong><span className="text-meta text-text-muted">waiting for signal</span></div>
                <div className="rounded-[16px] bg-medium-tint p-2.5"><strong className="num block text-kpi text-medium-fg">{held}</strong><span className="text-meta text-text-muted">kept on vehicle</span></div>
              </div>
              <p className="mt-3 flex items-start gap-2 text-body text-text-secondary"><ShieldCheck size={17} className="mt-0.5 shrink-0 text-ok-fg" />Raw audio, photos and uncertain facts stay local. Cloud AI calls: <strong>{s?.counters.cloud_ai_calls ?? 0}</strong>.</p>
            </section>
          </div>
        </div>
      </main>

      <footer className="flex min-h-[4.5rem] shrink-0 items-center gap-4 border-t border-border-subtle bg-accent-tint px-7">
        <span className="grid size-10 shrink-0 place-items-center rounded-full bg-accent-fill text-on-accent-fill"><Sparkles size={18} /></span>
        <div className="min-w-0 flex-1"><p className="label-caps text-herald-accent">Presenter cue</p><p className="truncate text-body font-semibold text-text-primary">{cueFor(s, attentionCount, hasConflict)}</p></div>
        <span className="hidden items-center gap-1 text-meta font-semibold text-herald-accent md:flex">Next: advance the replay <ArrowRight size={15} /></span>
      </footer>
    </div>
  );
}
