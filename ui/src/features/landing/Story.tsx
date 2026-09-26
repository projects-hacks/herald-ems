// The middle of the page: the headline numbers, how a call flows, and what Herald does.

import { ArrowRight, Signal } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { FEATURES, PROBLEM_CLOSER, PROBLEMS, STATS, STEPS, type Feature } from "./content";
import { Reveal, Section } from "./primitives";

export function Stats() {
  return (
    <section aria-label="Measured results at a glance" className="relative pb-8">
      <div className="lp-container">
        <ul className="grid grid-cols-4 overflow-hidden rounded-[20px] border border-border-subtle bg-surface-1 max-lg:grid-cols-2 max-sm:grid-cols-1">
          {STATS.map((s, i) => (
            <Reveal as="li" key={s.label} delay={i * 70}
              className={cn("px-6 py-7", i > 0 && "border-border-subtle lg:border-l",
                i % 2 === 1 && "sm:max-lg:border-l", i > 1 && "sm:max-lg:border-t", i > 0 && "max-sm:border-t")}>
              <p className="num text-[2.25rem] leading-none font-bold tracking-[-0.04em] text-text-primary max-sm:text-[1.875rem]">{s.value}</p>
              <p className="mt-2 text-[.9375rem] font-medium text-text-secondary">{s.label}</p>
              <p className="mt-3 text-[.8125rem] leading-snug text-text-muted">{s.source}</p>
            </Reveal>
          ))}
        </ul>
      </div>
    </section>
  );
}

export function Problem() {
  return (
    <Section id="why" eyebrow="Why it matters" title="The story gets lost on the way in"
      lede="The medic treats the patient while tracking what's captured, what's changing, what's due and what still has to be asked. Then the whole story is handed over out loud.">
      <div className="grid grid-cols-3 gap-4 max-lg:grid-cols-1">
        {PROBLEMS.map((p, i) => (
          <Reveal key={p.label} delay={i * 80}>
            <figure className="lp-card h-full p-7">
              <p className="num text-[2.75rem] leading-none font-bold tracking-[-0.045em] text-text-primary max-sm:text-[2.25rem]">{p.value}</p>
              <figcaption>
                <p className="mt-4 text-[1rem] leading-relaxed text-text-secondary">{p.label}</p>
                <p className="mt-5 border-t border-border-subtle pt-4 text-[.8125rem] text-text-muted">{p.source}</p>
              </figcaption>
            </figure>
          </Reveal>
        ))}
      </div>
      <Reveal delay={120}>
        <p className="mx-auto mt-14 max-w-[46rem] text-center text-[1.375rem] leading-snug font-semibold tracking-[-0.02em] text-balance text-text-primary max-sm:text-[1.1875rem]">
          {PROBLEM_CLOSER}
        </p>
      </Reveal>
    </Section>
  );
}

export function HowItWorks() {
  return (
    <Section id="how" eyebrow="How it works" title="From the first words to the ED, in four steps"
      lede="The medic keeps working. Herald writes the story as it is told, and asks only when it has to.">
      <ol className="relative grid grid-cols-4 gap-4 max-lg:grid-cols-2 max-sm:grid-cols-1">
        {STEPS.map((s, i) => {
          const Icon = s.icon;
          return (
            <Reveal as="li" key={s.title} delay={i * 90} className="relative">
              <div className="lp-card lp-card-hover h-full p-6">
                <div className="flex items-center justify-between">
                  <span className="lp-icon"><Icon size={22} aria-hidden /></span>
                  <span className="num text-[.8125rem] font-semibold text-text-muted">0{i + 1}</span>
                </div>
                <h3 className="mt-6 text-[1.1875rem] font-semibold tracking-[-0.02em]">{s.title}</h3>
                <p className="mt-2 text-[.9375rem] leading-relaxed text-text-secondary">{s.body}</p>
              </div>
              {i < STEPS.length - 1 && (
                <span aria-hidden className="absolute top-1/2 -right-[14px] z-10 hidden size-6 -translate-y-1/2 place-items-center rounded-full border border-border-subtle bg-bg text-herald-accent lg:grid">
                  <ArrowRight size={13} />
                </span>
              )}
            </Reveal>
          );
        })}
      </ol>
    </Section>
  );
}

/** Calls `start` once the element is at least 40% on screen, or `immediate` under reduced motion. */
function useOnScreen<T extends HTMLElement>(start: () => (() => void) | void, immediate: () => void) {
  const ref = useRef<T>(null);
  const handlers = useRef({ start, immediate });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches || document.documentElement.dataset.reducedMotion === "true" || typeof IntersectionObserver === "undefined") {
      handlers.current.immediate();
      return;
    }
    let stop: (() => void) | void;
    const io = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) { io.disconnect(); stop = handlers.current.start(); }
    }, { threshold: 0.4 });
    io.observe(el);
    return () => { io.disconnect(); stop?.(); };
  }, []);
  return ref;
}

/** The county checklist filling up: six segments close one by one once the card is on screen. */
function ChecklistVisual() {
  const [filled, setFilled] = useState(0);
  const ref = useOnScreen<HTMLDivElement>(() => {
    const timer = window.setInterval(() => setFilled((n) => Math.min(n + 1, 6)), 420);
    return () => window.clearInterval(timer);
  }, () => setFilled(6));
  const ready = filled === 6;
  return (
    <div ref={ref} className="mt-7 rounded-[14px] border border-border-subtle bg-bg/60 p-4" aria-hidden>
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-[.875rem] font-semibold">Stroke pre-alert</span>
        <span className="flex gap-[3px]">
          {Array.from({ length: 6 }, (_, i) => (
            <span key={i} className={cn("h-2.5 w-6 rounded-[4px] transition-colors duration-300 max-sm:w-4", i < filled ? "bg-herald-accent" : "bg-surface-3")} />
          ))}
        </span>
        <span className="num text-[.875rem] text-text-secondary">{filled} of 6</span>
        <span className={cn("ml-auto rounded-full px-2.5 py-0.5 text-[.75rem] font-semibold transition-colors",
          ready ? "bg-ok-tint text-ok-fg" : "bg-medium-tint text-medium-fg")}>{ready ? "ready" : "gaps open"}</span>
      </div>
    </div>
  );
}

/** A relay packet: critical facts first, inside a fixed byte budget. */
function PacketVisual() {
  const rows = [
    { tier: "Critical", fill: "bg-high-fill", w: "w-[46%]" },
    { tier: "Important", fill: "bg-medium-fill", w: "w-[30%]" },
    { tier: "Context", fill: "bg-low-fill", w: "w-[14%]" },
  ];
  return (
    <div className="mt-7 rounded-[14px] border border-border-subtle bg-bg/60 p-4" aria-hidden>
      <div className="flex items-center justify-between text-[.8125rem] text-text-muted">
        <span className="inline-flex items-center gap-2"><Signal size={14} className="text-medium-fg" /> Weak link</span>
        <span className="num">packet budget 420 B</span>
      </div>
      <div className="mt-3 flex h-3 gap-[2px] overflow-hidden rounded-[4px] bg-surface-3">
        {rows.map((r) => <span key={r.tier} className={cn("h-full", r.fill, r.w)} />)}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[.8125rem] text-text-secondary">
        {rows.map((r) => (
          <span key={r.tier} className="inline-flex items-center gap-2"><span className={cn("size-2 rounded-full", r.fill)} />{r.tier}</span>
        ))}
      </div>
    </div>
  );
}

function FeatureCard({ f, wide, visual, delay }: { f: Feature; wide?: boolean; visual?: ReactNode; delay: number }) {
  const Icon = f.icon;
  return (
    <Reveal delay={delay} className={cn(wide && "lg:col-span-2")}>
      <article className="lp-card lp-card-hover h-full p-6">
        <span className="lp-icon"><Icon size={21} aria-hidden /></span>
        <h3 className="mt-5 text-[1.0625rem] font-semibold tracking-[-0.015em]">{f.title}</h3>
        <p className="mt-2 max-w-[36rem] text-[.9375rem] leading-relaxed text-text-secondary">{f.body}</p>
        {visual}
      </article>
    </Reveal>
  );
}

/** Bento grid: the first and last features run wide with a small live visual; the rest fill the rows between. */
export function Features() {
  const first = FEATURES[0];
  const last = FEATURES[FEATURES.length - 1];
  const middle = FEATURES.slice(1, -1);
  return (
    <Section id="features" eyebrow="What it does" title="Everything the ED needs, nothing it doesn't"
      lede="A live, evidence-backed picture of the patient: what's known, what changed, what's still missing, and which clock is running.">
      <div className="grid grid-cols-3 gap-4 max-lg:grid-cols-2 max-sm:grid-cols-1">
        <FeatureCard f={first} wide visual={<ChecklistVisual />} delay={0} />
        {middle.map((f, i) => <FeatureCard key={f.title} f={f} delay={(i % 3) * 70} />)}
        <FeatureCard f={last} wide visual={<PacketVisual />} delay={70} />
      </div>
    </Section>
  );
}
