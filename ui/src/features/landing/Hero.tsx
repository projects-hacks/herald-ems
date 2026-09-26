import { ArrowRight, CloudOff, PlayCircle, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { HERO, LINKS } from "./content";
import { GitHubIcon, Logo, Reveal } from "./primitives";

const NAV = [
  { href: "#how", label: "How it works" },
  { href: "#features", label: "Features" },
  { href: "#trust", label: "Safety" },
  { href: "#results", label: "Results" },
];

export function Nav() {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 8);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  return (
    <header className="lp-nav" data-scrolled={scrolled}>
      <nav className="lp-container flex h-16 items-center gap-8" aria-label="Main">
        <a href="#top" aria-label="Herald home"><Logo /></a>
        <ul className="hidden items-center gap-7 md:flex">
          {NAV.map((n) => <li key={n.href}><a className="lp-navlink" href={n.href}>{n.label}</a></li>)}
        </ul>
        <div className="ml-auto flex items-center gap-2">
          <a className="lp-btn lp-btn-ghost lp-btn-sm max-sm:hidden" href={LINKS.source} target="_blank" rel="noreferrer">
            <GitHubIcon /> Source
          </a>
          <a className="lp-btn lp-btn-primary lp-btn-sm" href={LINKS.app}>Open Herald <ArrowRight size={15} aria-hidden /></a>
        </div>
      </nav>
    </header>
  );
}

function EcgTrace() {
  return (
    <svg className="lp-ecg mx-auto mt-8 h-10 w-full max-w-[34rem] text-herald-accent" viewBox="0 0 560 40" fill="none" aria-hidden>
      <path d="M0 22 H190 l10 -4 l8 4 H236 l6 8 l10 -28 l10 34 l7 -14 H300 l10 -6 l10 6 H560"
        stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Hero() {
  return (
    <section id="top" className="lp-hero">
      <div className="lp-hero-glow" />
      <div className="lp-hero-grid" />
      <div className="lp-container text-center">
        <Reveal>
          <span className="lp-pill"><span className="lp-pill-dot" /> {HERO.eyebrow}</span>
        </Reveal>
        <Reveal delay={80}>
          <h1 className="lp-h1 mx-auto mt-7 max-w-[15ch]">
            {HERO.titleLead} <span className="lp-gradient-text">{HERO.titleAccent}</span>
          </h1>
        </Reveal>
        <Reveal delay={160}>
          <p className="lp-lede mx-auto mt-6 text-[1.125rem]">{HERO.lede}</p>
        </Reveal>
        <Reveal delay={240} className="mt-9 flex flex-wrap items-center justify-center gap-3">
          <a className="lp-btn lp-btn-primary" href={LINKS.replay}><PlayCircle size={18} aria-hidden /> Watch a stroke call</a>
          <a className="lp-btn lp-btn-ghost" href="#how">How it works</a>
        </Reveal>
        <EcgTrace />
      </div>

      <div className="lp-container mt-6">
        <Reveal delay={200} className="relative mx-auto max-w-[1120px]">
          <div className="lp-float left-[-26px] top-[86%] max-lg:hidden">
            <span className="lp-icon size-9 rounded-[10px]"><CloudOff size={18} aria-hidden /></span>
            <span className="text-left">
              <span className="block text-[.75rem] font-semibold tracking-[.08em] text-text-muted uppercase">Cloud AI calls</span>
              <span className="num block text-[1.125rem] font-bold">0</span>
            </span>
          </div>
          <div className="lp-float right-[-26px] top-[56%] max-lg:hidden">
            <span className="grid size-9 place-items-center rounded-[10px] bg-ok-tint text-ok-fg"><ShieldCheck size={18} aria-hidden /></span>
            <span className="text-left">
              <span className="block text-[.75rem] font-semibold tracking-[.08em] text-text-muted uppercase">Leaves the vehicle</span>
              <span className="block text-[.9375rem] font-semibold">Confirmed facts only</span>
            </span>
          </div>
          <figure className="lp-shot">
            <div className="lp-shot-inner">
              <div className="lp-shot-bar" aria-hidden>
                <i /><i /><i />
                <span className="mx-auto rounded-md bg-surface-2 px-3 py-0.5 text-[.75rem] text-text-muted">herald · NOW · recorded stroke call</span>
              </div>
              <img src={HERO.image.src} width={HERO.image.width} height={HERO.image.height} alt={HERO.image.alt}
                className="block h-auto w-full" fetchPriority="high" />
            </div>
            <div className="lp-shot-fade" />
          </figure>
        </Reveal>
      </div>
    </section>
  );
}
