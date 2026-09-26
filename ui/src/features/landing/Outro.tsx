// The end of the page: the edge hardware and model stack, the closing call to action, and the footer.

import { ArrowRight, Cpu, Gauge, Lock, PlayCircle, WifiOff } from "lucide-react";
import { DISCLAIMER, HARDWARE_FACTS, LINKS, STACK, TELEMETRY } from "./content";
import { GitHubIcon, Logo, Reveal, Section } from "./primitives";

const EDGE_POINTS = [
  { icon: WifiOff, title: "Works with no signal", body: "Dead zones, basements, disasters. The copilot never waits for a network." },
  { icon: Lock, title: "Sensitive data stays", body: "Audio and photos from inside a patient's home never leave the vehicle." },
];

export function Edge() {
  return (
    <Section id="edge" eyebrow="Built for the edge" title="One box in the vehicle. No cloud AI."
      lede="Every model runs on a single HP ZGX Nano with an NVIDIA GB10. The only network use is the county protocol sync and the relay to the ED, when a link exists.">
      <div className="grid grid-cols-[1fr_1.15fr] gap-4 max-lg:grid-cols-1">
        <Reveal>
          <div className="lp-card relative flex h-full flex-col overflow-hidden p-7">
            <div aria-hidden className="absolute -top-24 -right-24 size-72 rounded-full bg-[radial-gradient(circle,var(--orb-a),transparent_70%)]" />
            <span className="lp-icon"><Cpu size={22} aria-hidden /></span>
            <p className="mt-6 text-[.8125rem] font-semibold tracking-[.1em] text-text-muted uppercase">Hardware</p>
            <p className="mt-1 text-[1.75rem] leading-tight font-bold tracking-[-0.03em]">HP ZGX Nano</p>
            <p className="text-[1.0625rem] text-text-secondary">NVIDIA GB10 · unified memory</p>
            <div className="mt-7 space-y-5">
              {EDGE_POINTS.map((p) => {
                const Icon = p.icon;
                return (
                  <div key={p.title} className="flex gap-3.5">
                    <Icon size={19} className="mt-0.5 shrink-0 text-herald-accent" aria-hidden />
                    <div>
                      <p className="text-[.9375rem] font-semibold">{p.title}</p>
                      <p className="text-[.875rem] leading-relaxed text-text-secondary">{p.body}</p>
                    </div>
                  </div>
                );
              })}
            </div>
            <dl className="mt-auto grid grid-cols-2 gap-4 border-t border-border-subtle pt-6 max-lg:mt-8">
              {HARDWARE_FACTS.map((f) => (
                <div key={f.label}>
                  <dt className="sr-only">{f.label}</dt>
                  <dd className="num text-[1.5rem] leading-none font-bold tracking-[-0.03em]">{f.value}</dd>
                  <dd className="mt-1.5 text-[.8125rem] text-text-muted">{f.label}</dd>
                </div>
              ))}
            </dl>
          </div>
        </Reveal>
        <div className="grid gap-4">
          <Reveal delay={80}>
            <div className="lp-card p-6">
              <p className="text-[.8125rem] font-semibold tracking-[.1em] text-text-muted uppercase">The model stack, all local</p>
              <ul className="mt-4 divide-y divide-border-subtle">
                {STACK.map((s) => (
                  <li key={s.job} className="flex items-center justify-between gap-4 py-3 max-sm:flex-col max-sm:items-start max-sm:gap-0.5">
                    <span className="text-[.875rem] text-text-muted">{s.job}</span>
                    <span className="text-right text-[.9375rem] font-semibold max-sm:text-left">{s.model}</span>
                  </li>
                ))}
              </ul>
            </div>
          </Reveal>
          <Reveal delay={140}>
            <div className="lp-card flex items-start gap-4 p-6">
              <span className="lp-icon shrink-0"><Gauge size={21} aria-hidden /></span>
              <div>
                <p className="text-[1.0625rem] font-semibold">Telemetry you can check</p>
                <ul className="mt-2 flex flex-wrap gap-2">
                  {TELEMETRY.map((t) => (
                    <li key={t} className="rounded-full border border-border-subtle bg-bg/60 px-3 py-1 text-[.8125rem] text-text-secondary">{t}</li>
                  ))}
                  <li className="rounded-full bg-ok-tint px-3 py-1 text-[.8125rem] font-semibold text-ok-fg">Cloud AI calls: 0</li>
                </ul>
              </div>
            </div>
          </Reveal>
        </div>
      </div>
    </Section>
  );
}

export function Closing() {
  return (
    <section className="lp-section pt-8" aria-labelledby="cta-title">
      <div className="lp-container">
        <Reveal>
          <div className="relative isolate overflow-hidden rounded-[28px] border border-glass-border-hi px-8 py-20 text-center max-sm:px-5 max-sm:py-14">
            <div aria-hidden className="absolute inset-0 -z-10 bg-[radial-gradient(60%_80%_at_50%_0%,var(--orb-a),transparent_70%),radial-gradient(50%_70%_at_50%_100%,var(--orb-b),transparent_70%)] bg-surface-1" />
            <div aria-hidden className="lp-hero-grid !inset-0 !h-full opacity-60" />
            <h2 id="cta-title" className="lp-h2 mx-auto max-w-[20ch]">See a stroke call, start to finish.</h2>
            <p className="lp-lede mx-auto mt-4">
              A recorded scenario replays in the real app: the checklist closes, the county routing rule appears, and every finding links back to the words it was heard in.
            </p>
            <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
              <a className="lp-btn lp-btn-primary" href={LINKS.replay}><PlayCircle size={18} aria-hidden /> Watch the replay</a>
              <a className="lp-btn lp-btn-ghost" href={LINKS.app}>Open Herald <ArrowRight size={16} aria-hidden /></a>
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
        <p className="text-[.8125rem] text-text-muted">{DISCLAIMER} It never recommends treatment; the paramedic decides.</p>
        <a className="lp-navlink ml-auto inline-flex items-center gap-2 max-md:ml-0" href={LINKS.source} target="_blank" rel="noreferrer">
          <GitHubIcon /> Source on GitHub
        </a>
      </div>
    </footer>
  );
}
