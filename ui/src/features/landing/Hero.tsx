// The top of the page: the navigation and the hero, with the real medic screen on a tablet tilted in 3D. The tablet
// flattens as the page scrolls and leans toward the pointer; under reduced motion it holds one gentle tilt.

import { ArrowRight, AudioLines, Camera, CloudOff, PlayCircle, RadioTower, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { HERO, LINKS, SHOTS } from "./content";
import { GitHubIcon, Logo, Tablet, useReducedMotion } from "./primitives";

const NAV = [
  { href: "#journey", label: "How it works" },
  { href: "#features", label: "Features" },
  { href: "#results", label: "Results" },
  { href: "#trust", label: "Safety" },
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
      <nav className="lp-container flex h-[68px] items-center gap-8" aria-label="Main">
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
    <svg className="lp-ecg" viewBox="0 0 1200 60" preserveAspectRatio="none" fill="none" aria-hidden>
      <path d="M0 34 H420 l12 -6 l10 6 H486 l8 10 l14 -40 l14 48 l9 -18 H560 l12 -8 l12 8 H1200"
        stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/** Scroll (0 at the top, 1 after most of a screen) and pointer position, written as CSS variables on the stage. */
function useStageMotion(reduced: boolean) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (reduced) { el.style.setProperty("--s", "0.45"); el.style.setProperty("--mx", "0"); el.style.setProperty("--my", "0"); return; }
    let frame = 0;
    let mx = 0, my = 0;
    const paint = () => {
      frame = 0;
      const vh = window.innerHeight || 1;
      el.style.setProperty("--s", Math.min(1, window.scrollY / (vh * 0.75)).toFixed(3));
      el.style.setProperty("--mx", mx.toFixed(3));
      el.style.setProperty("--my", my.toFixed(3));
    };
    const schedule = () => { if (!frame) frame = requestAnimationFrame(paint); };
    const onMove = (e: PointerEvent) => {
      if (e.pointerType !== "mouse") return;
      mx = (e.clientX / window.innerWidth) * 2 - 1;
      my = (e.clientY / window.innerHeight) * 2 - 1;
      schedule();
    };
    paint();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => {
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      window.removeEventListener("pointermove", onMove);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [reduced]);
  return ref;
}

/** Glass chips floating in front of the tablet at different depths: what Herald did on its own during the call. */
function Chips() {
  return (
    <div className="lp-chips" aria-hidden>
      <div className="lp-chip lp-chip-a">
        <div className="lp-chip-in">
          <span className="lp-chip-icon"><AudioLines size={16} /></span>
          <span>
            <span className="lp-chip-k">Heard · medic</span>
            <span className="lp-chip-v">“left arm and leg can't lift”</span>
            <span className="lp-chip-tag">Arm or leg weakness · 1</span>
          </span>
        </div>
      </div>
      <div className="lp-chip lp-chip-b">
        <div className="lp-chip-in">
          <span className="lp-chip-icon"><Camera size={16} /></span>
          <span>
            <span className="lp-chip-k">Read from the monitor</span>
            <span className="lp-chip-vitals">
              <span><b className="num">88</b> HR</span><span><b className="num">148/92</b> BP</span><span><b className="num">96%</b> SpO₂</span>
            </span>
          </span>
        </div>
      </div>
      <div className="lp-chip lp-chip-c">
        <div className="lp-chip-in">
          <span className="lp-chip-icon lp-chip-icon-ok"><ShieldCheck size={16} /></span>
          <span>
            <span className="lp-chip-k">Stroke alert</span>
            <span className="lp-chip-bar"><i /><i /><i /><i /><i /><i /></span>
            <span className="lp-chip-v">6 of 6 · ready</span>
          </span>
        </div>
      </div>
      <div className="lp-chip lp-chip-d">
        <div className="lp-chip-in">
          <span className="lp-chip-icon"><RadioTower size={16} /></span>
          <span>
            <span className="lp-chip-k">Pre-alert sent</span>
            <span className="lp-chip-v">Regional ED · acknowledged</span>
          </span>
        </div>
      </div>
      <div className="lp-chip lp-chip-e">
        <div className="lp-chip-in">
          <span className="lp-chip-icon"><CloudOff size={16} /></span>
          <span>
            <span className="lp-chip-k">Cloud calls</span>
            <span className="lp-chip-big num">0</span>
          </span>
        </div>
      </div>
    </div>
  );
}

export function Hero() {
  const reduced = useReducedMotion();
  const stage = useStageMotion(reduced);
  return (
    <section id="top" className="lp-hero">
      <div className="lp-hero-glow" aria-hidden />
      <div className="lp-hero-grid" aria-hidden />
      <div className="lp-container relative text-center">
        <span className="lp-pill"><span className="lp-pill-dot" /> {HERO.eyebrow}</span>
        <h1 className="lp-h1 mx-auto mt-8">
          {HERO.titleLead} <span className="lp-gradient-text">{HERO.titleAccent}</span>
        </h1>
        <p className="lp-lede lp-hero-lede mx-auto mt-7">{HERO.lede}</p>
        <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
          <a className="lp-btn lp-btn-primary lp-btn-lg" href={LINKS.app}>{HERO.primary} <ArrowRight size={18} aria-hidden /></a>
          <a className="lp-btn lp-btn-ghost lp-btn-lg" href={LINKS.replay}><PlayCircle size={19} aria-hidden /> {HERO.secondary}</a>
        </div>
        <ul className="lp-hero-ticks mt-7">
          <li><ShieldCheck size={15} aria-hidden /> 0 cloud calls</li>
          <li><ShieldCheck size={15} aria-hidden /> Works with no signal</li>
          <li><ShieldCheck size={15} aria-hidden /> The medic decides</li>
        </ul>
      </div>

      <div ref={stage} className="lp-stage" data-motion={reduced ? "off" : "on"}>
        <EcgTrace />
        <div className="lp-stage-enter">
          <div className="lp-rig">
            <Tablet shot={SHOTS.medic} priority />
            <Chips />
          </div>
          <div className="lp-rig-shadow" aria-hidden />
        </div>
      </div>
    </section>
  );
}
