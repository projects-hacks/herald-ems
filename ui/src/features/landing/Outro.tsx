// The end of the page: the edge hardware, the closing call to action, and the footer.

import { ArrowRight, Cpu, Gauge, Lock, PlayCircle, WifiOff } from "lucide-react";
import { FOOTER_NOTE, HARDWARE_FACTS, HERO, LINKS, TELEMETRY } from "./content";
import { GitHubIcon, Logo, Reveal, Section } from "./primitives";

const EDGE_POINTS = [
  { icon: WifiOff, title: "Works with no signal", body: "Dead zones, basements, disasters. The copilot never waits for a network; the ED catches up the moment a link returns." },
  { icon: Lock, title: "Patient data stays in the vehicle", body: "Audio and photos from inside a patient's home never leave the box. Only confirmed facts go to the hospital." },
  { icon: Gauge, title: "Telemetry you can check", body: TELEMETRY.join(" · ") + "." },
];

export function Edge() {
  return (
    <Section id="edge" eyebrow="Built for the edge" title="One box in the vehicle. Zero cloud calls."
      lede="Every model runs on a single HP ZGX Nano with an NVIDIA GB10. The only network traffic is the county protocol sync and the relay to the ED, whenever a link exists.">
      <Reveal>
        <div className="lp-edge">
          <div className="lp-edge-hw">
            <div aria-hidden className="lp-edge-orb" />
            <div className="lp-chipcube" aria-hidden><Cpu size={40} strokeWidth={1.6} /></div>
            <p className="mt-7 text-[.8125rem] font-semibold tracking-[.1em] text-text-muted uppercase">Hardware</p>
            <p className="mt-1 text-[2rem] leading-tight font-bold tracking-[-0.03em]">HP ZGX Nano</p>
            <p className="text-[1.0625rem] text-text-secondary">NVIDIA GB10 · unified memory</p>
            <dl className="mt-8 grid grid-cols-3 gap-4 border-t border-[color:var(--glass-border)] pt-6">
              {HARDWARE_FACTS.map((f) => (
                <div key={f.label}>
                  <dt className="sr-only">{f.label}</dt>
                  <dd className="num text-[1.625rem] leading-none font-bold tracking-[-0.03em] max-sm:text-[1.25rem]">{f.value}</dd>
                  <dd className="mt-1.5 text-[.8125rem] leading-snug text-text-muted">{f.label}</dd>
                </div>
              ))}
            </dl>
          </div>
          <ul className="lp-edge-points">
            {EDGE_POINTS.map((p) => {
              const Icon = p.icon;
              return (
                <li key={p.title} className="flex gap-4">
                  <span className="lp-icon shrink-0"><Icon size={20} aria-hidden /></span>
                  <div>
                    <p className="text-[1.0625rem] font-semibold">{p.title}</p>
                    <p className="mt-1 text-[.9375rem] leading-relaxed text-text-secondary">{p.body}</p>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      </Reveal>
    </Section>
  );
}

export function Closing() {
  return (
    <section className="lp-section pt-4" aria-labelledby="cta-title">
      <div className="lp-container">
        <Reveal>
          <div className="lp-cta">
            <div aria-hidden className="lp-hero-grid !inset-0 !h-full opacity-60" />
            <h2 id="cta-title" className="lp-h2 mx-auto max-w-[20ch]">See a stroke call, start to finish.</h2>
            <p className="lp-lede mx-auto mt-5">
              Open Herald and talk to it, or watch the recorded call replay in the real app: the checklist closes, the county rule picks the hospital, and every finding links back to the words it was heard in.
            </p>
            <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
              <a className="lp-btn lp-btn-primary lp-btn-lg" href={LINKS.app}>{HERO.primary} <ArrowRight size={18} aria-hidden /></a>
              <a className="lp-btn lp-btn-ghost lp-btn-lg" href={LINKS.replay}><PlayCircle size={19} aria-hidden /> {HERO.secondary}</a>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

export function Footer() {
  return (
    <footer className="border-t border-border-subtle">
      <div className="lp-container flex flex-wrap items-center gap-x-8 gap-y-4 py-10">
        <Logo />
        <p className="text-[.8125rem] text-text-muted">{FOOTER_NOTE}</p>
        <a className="lp-navlink ml-auto inline-flex items-center gap-2 max-md:ml-0" href={LINKS.source} target="_blank" rel="noreferrer">
          <GitHubIcon /> Source on GitHub
        </a>
      </div>
    </footer>
  );
}
