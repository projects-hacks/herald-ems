// What Herald does today: a bento grid in the order a call unfolds (each card with a small illustration of the real
// behaviour), the handover spotlight with the ED board's final report, and the smaller capabilities underneath.
// The illustrations are examples, not recordings; the screenshots elsewhere on the page are the real app.

import { Check, CheckCircle2, Hand, Mic, Signal, Users, X } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { ALSO, FEATURES, SHOTS, type Feature } from "./content";
import { Board, Reveal, Section } from "./primitives";

function Well({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("lp-well", className)} aria-hidden>{children}</div>;
}

function MicVisual() {
  const rows = [
    { who: "Medic", icon: Mic, said: "BP one forty-eight over ninety-two", out: "BP 148/92", kind: "ok" },
    { who: "Wife", icon: Users, said: "He's allergic to penicillin", out: "Allergy · 1 tap", kind: "tap" },
    { who: "Partner", icon: Users, said: "Grab the stair chair, I'll get the door", out: "Chatter · not logged", kind: "drop" },
    { who: "Patient", icon: Users, said: "My left arm feels heavy", out: "Arm weakness", kind: "ok" },
  ] as const;
  return (
    <Well>
      <ul className="space-y-2">
        {rows.map((r) => (
          <li key={r.said} className={cn("lp-said", r.kind === "drop" && "is-drop")}>
            <span className="lp-said-who"><r.icon size={13} /> {r.who}</span>
            <span className="lp-said-text">“{r.said}”</span>
            <span className={cn("lp-said-out", `is-${r.kind}`)}>{r.out}</span>
          </li>
        ))}
      </ul>
    </Well>
  );
}

function CheckVisual() {
  return (
    <Well>
      <p className="text-[.75rem] font-semibold tracking-[.1em] text-text-muted uppercase">Heard · medic</p>
      <p className="mt-1.5 text-[.9375rem] leading-snug text-text-primary">“<mark className="lp-mark">No chest pain</mark>, but she's been <mark className="lp-mark">short of breath</mark> since this morning.”</p>
      <div className="mt-3.5 grid gap-2">
        <div className="lp-verdict is-keep">
          <CheckCircle2 size={16} /> <span className="flex-1">Short of breath · <b>yes</b></span> <span className="lp-verdict-why">stated · recorded</span>
        </div>
        <div className="lp-verdict is-drop">
          <X size={16} /> <span className="flex-1 line-through decoration-1">Chest pain · yes</span> <span className="lp-verdict-why">the words say no · dropped</span>
        </div>
        <div className="lp-verdict is-tap">
          <Hand size={16} /> <span className="flex-1">Name, allergies, meds, drugs given, code status</span> <span className="lp-verdict-why">always one tap</span>
        </div>
      </div>
    </Well>
  );
}

const VITALS: { k: string; v: string; u?: string; pts: string }[] = [
  { k: "HR", v: "88", pts: "0,14 10,12 20,13 30,9 40,10 50,8 60,9" },
  { k: "BP", v: "148/92", pts: "0,6 10,7 20,6 30,8 40,9 50,10 60,11" },
  { k: "SpO₂", v: "96", u: "%", pts: "0,12 10,11 20,9 30,8 40,7 50,7 60,6" },
  { k: "RR", v: "18", pts: "0,8 10,9 20,8 30,10 40,9 50,10 60,9" },
  { k: "EtCO₂", v: "38", pts: "0,11 10,10 20,10 30,9 40,9 50,8 60,8" },
];

function MonitorVisual() {
  return (
    <Well>
      <div className="grid grid-cols-3 gap-1.5">
        {VITALS.map((v) => (
          <div key={v.k} className="lp-vital">
            <span className="text-[.6875rem] font-semibold tracking-[.08em] text-text-muted">{v.k}</span>
            <span className="num text-[1.0625rem] leading-tight font-bold text-text-primary">{v.v}{v.u && <small className="text-[.6875rem] font-medium text-text-muted">{v.u}</small>}</span>
            <svg viewBox="0 0 60 18" preserveAspectRatio="none" className="lp-spark"><polyline points={v.pts} /></svg>
          </div>
        ))}
        <div className="lp-vital lp-vital-held">
          <span className="text-[.6875rem] font-semibold tracking-[.08em] text-medium-fg">SpO₂ 46?</span>
          <span className="text-[.8125rem] leading-tight font-bold text-text-primary">Jump held</span>
          <span className="text-[.6875rem] text-text-secondary">not charted</span>
        </div>
      </div>
      <p className="mt-2.5 inline-flex items-center gap-2 text-[.8125rem] text-text-secondary"><span className="lp-live-dot" /> Read 4 s ago · every ~15 s · into live trends</p>
    </Well>
  );
}

function ProtocolVisual() {
  return (
    <Well>
      <p className="lp-ask"><Mic size={14} /> “Show me the protocol for STEMI”</p>
      <blockquote className="lp-quote">
        “Transmission of 12-lead ECG and STEMI Alert advanced notification to receiving hospital”
      </blockquote>
      <p className="mt-2 text-[.75rem] leading-snug text-text-muted">Santa Clara County EMS · 700-A08 Chest Pain · §1.4 · page 1 · effective Jan 1, 2025</p>
    </Well>
  );
}

function RouteVisual() {
  return (
    <Well className="!p-0 overflow-hidden">
      <svg viewBox="0 0 300 96" className="lp-map">
        <path className="lp-map-road" d="M0 70 H300 M60 0 V96 M190 0 V96 M0 22 H300" />
        <path className="lp-map-route" d="M28 78 H60 V46 Q60 38 68 38 H190 V18 H258" />
        <circle className="lp-map-from" cx="28" cy="78" r="5" />
        <circle className="lp-map-to" cx="262" cy="18" r="7" />
      </svg>
      <div className="border-t border-border-subtle px-3.5 py-3">
        <p className="text-[.75rem] text-text-muted">Suggested from county rules · STEMI center</p>
        <p className="text-[.9375rem] font-semibold text-text-primary">Valley Medical Center</p>
        <div className="mt-2 flex items-center gap-3">
          <p className="num text-[1.125rem] leading-none font-bold text-herald-accent">10 min <span className="text-[.75rem] font-medium text-text-muted">by road</span></p>
          <span className="ml-auto rounded-full bg-accent-fill px-3.5 py-1 text-[.8125rem] font-bold text-on-accent-fill">Accept</span>
        </div>
      </div>
    </Well>
  );
}

function RelayVisual() {
  const rows = [
    { tier: "Critical", fill: "bg-high-fill", w: "46%" },
    { tier: "Important", fill: "bg-medium-fill", w: "30%" },
    { tier: "Context", fill: "bg-low-fill", w: "14%" },
  ];
  return (
    <Well>
      <div className="flex items-center justify-between text-[.8125rem] text-text-secondary">
        <span className="inline-flex items-center gap-2"><Signal size={14} className="text-medium-fg" /> Weak link · 50% loss</span>
        <span className="num text-text-muted">420 B packet</span>
      </div>
      <div className="lp-packet mt-3">
        {rows.map((r, i) => <span key={r.tier} className={cn("lp-packet-seg", r.fill)} style={{ width: r.w, animationDelay: `${i * 0.25}s` }} />)}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-[.8125rem] text-text-secondary">
        {rows.map((r) => <span key={r.tier} className="inline-flex items-center gap-2"><span className={cn("size-2 rounded-full", r.fill)} />{r.tier}</span>)}
        <span className="ml-auto inline-flex items-center gap-1.5 font-semibold text-ok-fg"><Check size={14} /> 0 lost · 0 duplicates</span>
      </div>
    </Well>
  );
}

function EdVisual() {
  return (
    <Well>
      <div className="flex flex-wrap items-center gap-3">
        <span className="rounded-[8px] bg-high-fill px-2.5 py-1 text-[.8125rem] font-extrabold tracking-[.04em] text-high-on-fill">STEMI ALERT</span>
        <span className="text-[.875rem] text-text-secondary">Pre-alert 5/5 ready</span>
        <span className="ml-auto text-right"><b className="num text-[1.25rem] font-bold text-herald-accent">10 min</b> <span className="text-[.75rem] text-text-muted">road ETA</span></span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-1.5 text-[.8125rem]">
        {["Allergies · penicillin", "Anticoagulant", "Code status", "Medications · 2"].map((t) => <span key={t} className="lp-strip">{t}</span>)}
      </div>
      <div className="lp-answer mt-3">
        <CheckCircle2 size={16} /> <span className="font-semibold">Cath lab activated</span> <span className="ml-auto text-text-muted">→ back to the ambulance</span>
      </div>
    </Well>
  );
}

const VISUALS: Record<string, ReactNode> = {
  "Hands-free room microphone": <MicVisual />,
  "An agentic check on every fact": <CheckVisual />,
  "The monitor camera": <MonitorVisual />,
  "County protocols on voice": <ProtocolVisual />,
  "Destination and road ETA": <RouteVisual />,
  "ED pre-alert over a weak link": <RelayVisual />,
  "The ED board": <EdVisual />,
};

// Six-column bento: wide, wide / three across / wide, wide.
const SPANS = ["lg:col-span-3", "lg:col-span-3", "lg:col-span-2", "lg:col-span-2", "lg:col-span-2", "lg:col-span-3", "lg:col-span-3"];

function FeatureCard({ f, span, delay }: { f: Feature; span: string; delay: number }) {
  const Icon = f.icon;
  return (
    <Reveal delay={delay} className={span}>
      <article className="lp-card lp-card-hover flex h-full flex-col p-7 max-sm:p-5">
        <div className="flex items-center gap-3">
          <span className="lp-icon"><Icon size={21} aria-hidden /></span>
          {f.tag && <span className="lp-tag">{f.tag}</span>}
        </div>
        <h3 className="mt-5 text-[1.25rem] font-semibold tracking-[-0.02em]">{f.title}</h3>
        <p className="mt-2 max-w-[38rem] text-[.9375rem] leading-relaxed text-text-secondary">{f.body}</p>
        <div className="mt-auto pt-6">{VISUALS[f.title]}</div>
      </article>
    </Reveal>
  );
}

export function Features() {
  const grid = FEATURES.filter((f) => f.title !== "One-tap handover");
  return (
    <Section id="features" eyebrow="What it does today" title="Everything the ED needs, captured while the medic works"
      lede="Hands-free from the first word to the handover. Herald hears, reads, checks, finds and sends on its own, and asks only when it has to.">
      <div className="grid grid-cols-6 gap-5 max-lg:grid-cols-2 max-sm:grid-cols-1">
        {grid.map((f, i) => <FeatureCard key={f.title} f={f} span={SPANS[i] ?? "lg:col-span-2"} delay={(i % 3) * 70} />)}
      </div>
    </Section>
  );
}

export function Handover() {
  const f = FEATURES.find((x) => x.title === "One-tap handover")!;
  const Icon = f.icon;
  return (
    <section id="handover" className="lp-section pt-0" aria-labelledby="handover-title">
      <div className="lp-container">
        <div className="lp-spot">
          <div className="lp-spot-copy">
            <span className="lp-icon"><Icon size={22} aria-hidden /></span>
            <p className="lp-eyebrow mt-6">At the door</p>
            <h2 id="handover-title" className="lp-h2 !text-[clamp(1.75rem,3vw,2.5rem)]">One tap. The report is already on the board.</h2>
            <p className="lp-lede mt-4">{f.body}</p>
            <ul className="mt-6 space-y-2.5 text-[.9375rem] text-text-secondary">
              {["MIST for trauma, SBAR for medical calls", "Read aloud, frozen at handover, confirmed facts only", "The ED confirms receipt; the crew starts the next patient"].map((t) => (
                <li key={t} className="flex items-start gap-3"><CheckCircle2 size={18} className="mt-0.5 shrink-0 text-ok-fg" aria-hidden />{t}</li>
              ))}
            </ul>
          </div>
          <div className="lp-spot-shot">
            <Board shot={SHOTS.edHandover} className="lp-spot-board" />
          </div>
        </div>

        <ul className="mt-6 grid grid-cols-4 gap-4 max-lg:grid-cols-2 max-sm:grid-cols-1">
          {ALSO.map((a, i) => {
            const AIcon = a.icon;
            return (
              <Reveal as="li" key={a.title} delay={i * 60}>
                <div className="lp-mini h-full">
                  <AIcon size={19} className="shrink-0 text-herald-accent" aria-hidden />
                  <div>
                    <p className="text-[.9375rem] font-semibold">{a.title}</p>
                    <p className="mt-1 text-[.8125rem] leading-relaxed text-text-secondary">{a.body}</p>
                  </div>
                </div>
              </Reveal>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
