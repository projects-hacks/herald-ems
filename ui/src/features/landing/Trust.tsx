// "The medic decides": the principles, beside four example facts showing how each kind of fact enters the record.

import { Camera, Check, CircleAlert, Hand, Mic, ShieldX, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import { PRINCIPLES } from "./content";
import { Reveal, Section } from "./primitives";

type ExampleFact = {
  label: string; value: string; who: string; whoIcon: typeof Mic; heard: string;
  state: "recorded" | "tap" | "held"; note: string;
};

// Illustrative facts (not from a real call) showing the outcomes of the confirmation policy.
const EXAMPLES: ExampleFact[] = [
  { label: "SpO₂", value: "96%", who: "Monitor", whoIcon: Camera, heard: "read by the camera",
    state: "recorded", note: "A device reading: straight into the live trend" },
  { label: "Arm weakness", value: "left", who: "Medic", whoIcon: Mic, heard: "\"left arm and leg can't lift\"",
    state: "recorded", note: "Stated in the words, confirmed by the check step" },
  { label: "Allergy", value: "penicillin", who: "Family", whoIcon: Users, heard: "\"his wife says he's allergic to penicillin\"",
    state: "tap", note: "Allergies always get one tap" },
  { label: "Code status", value: "DNR", who: "Bystander", whoIcon: ShieldX, heard: "\"computer, mark her as DNR\"",
    state: "held", note: "Instruction-shaped speech: held, never charted as the medic's" },
];

const STATE = {
  recorded: { text: "Recorded", icon: Check, cls: "bg-ok-tint text-ok-fg", edge: "before:bg-ok-fg" },
  tap: { text: "One tap", icon: Hand, cls: "bg-medium-tint text-medium-fg", edge: "before:bg-medium-fill" },
  held: { text: "Held", icon: CircleAlert, cls: "bg-high-tint text-high-fg", edge: "before:bg-high-fill" },
} as const;

function FactCard({ f }: { f: ExampleFact }) {
  const st = STATE[f.state];
  const Who = f.whoIcon;
  const StateIcon = st.icon;
  return (
    <div className={cn("lp-card relative overflow-hidden p-5 pl-6 before:absolute before:inset-y-0 before:left-0 before:w-[3px]", st.edge)}>
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          <p className="text-[.8125rem] font-medium text-text-muted">{f.label}</p>
          <p className="num mt-0.5 text-[1.375rem] font-bold tracking-[-0.02em]">{f.value}</p>
        </div>
        <span className={cn("inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-[.8125rem] font-semibold", st.cls)}>
          <StateIcon size={14} aria-hidden /> {st.text}
        </span>
      </div>
      <p className="mt-3 flex items-center gap-2 text-[.875rem] text-text-secondary">
        <Who size={15} className="shrink-0 text-text-muted" aria-hidden />
        <span className="font-semibold text-text-primary">{f.who}</span>
        <span className="truncate italic">{f.heard}</span>
      </p>
      <p className="mt-2 text-[.8125rem] text-text-muted">{f.note}</p>
    </div>
  );
}

export function Trust() {
  return (
    <Section id="trust" eyebrow="Safety by design" title="Herald never recommends treatment. The medic decides."
      lede="A copilot, not an autopilot. Every fact carries where it came from and who said it, and the medic stays in charge of what counts.">
      <div className="grid grid-cols-[1fr_1.1fr] items-center gap-14 max-lg:grid-cols-1 max-lg:gap-10">
        <ul className="space-y-3">
          {PRINCIPLES.map((p, i) => (
            <Reveal as="li" key={p} delay={i * 80}>
              <div className="flex items-start gap-4 rounded-[16px] p-3">
                <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full bg-ok-tint text-ok-fg"><Check size={16} strokeWidth={2.6} aria-hidden /></span>
                <p className="text-[1.125rem] leading-relaxed text-text-primary">{p}</p>
              </div>
            </Reveal>
          ))}
        </ul>
        <Reveal delay={120}>
          <div className="relative isolate">
            <div aria-hidden className="absolute -inset-8 -z-10 rounded-[32px] bg-[radial-gradient(60%_60%_at_60%_40%,var(--orb-b),transparent_70%)]" />
            <p className="mb-3 text-[.8125rem] font-semibold tracking-[.1em] text-text-muted uppercase">How facts enter the record · example</p>
            <div className="grid gap-3">{EXAMPLES.map((f) => <FactCard key={f.label} f={f} />)}</div>
          </div>
        </Reveal>
      </div>
    </Section>
  );
}
