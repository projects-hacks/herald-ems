// Small building blocks shared by the landing sections: the brand mark, section frame, device frames, scroll reveal
// and the motion hooks. Nothing here hides content: every section is fully visible at rest, and motion only moves
// things that are already on screen (or about to be), never fades them in from nothing.

import { Activity } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { cn } from "@/lib/utils";
import type { Shot } from "./content";

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5 text-[1.25rem] font-[750] tracking-[-0.055em] text-text-primary", className)}>
      <span className="lp-logo-mark">
        <Activity size={20} strokeWidth={2.4} aria-hidden />
      </span>
      <span>herald<span className="text-herald-accent">.</span></span>
    </span>
  );
}

export function GitHubIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="currentColor" aria-hidden>
      <path d="M8 0C3.58 0 0 3.58 0 8a8 8 0 0 0 5.47 7.59c.4.07.55-.17.55-.38v-1.33c-2.23.48-2.7-1.07-2.7-1.07-.36-.92-.89-1.17-.89-1.17-.73-.5.05-.49.05-.49.8.06 1.23.83 1.23.83.72 1.22 1.87.87 2.33.66.07-.52.28-.87.5-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 7.6 0 0 1 4 0c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48v2.2c0 .21.15.46.55.38A8 8 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
    </svg>
  );
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="lp-eyebrow">{children}</p>;
}

export function Section({ id, eyebrow, title, lede, children, className }: {
  id?: string; eyebrow: string; title: ReactNode; lede?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section id={id} className={cn("lp-section", className)} aria-labelledby={id ? `${id}-title` : undefined}>
      <div className="lp-container">
        <Reveal className="mx-auto max-w-[48rem] text-center">
          <Eyebrow>{eyebrow}</Eyebrow>
          <h2 id={id ? `${id}-title` : undefined} className="lp-h2">{title}</h2>
          {lede && <p className="lp-lede mx-auto mt-5">{lede}</p>}
        </Reveal>
        <div className="mt-16 max-sm:mt-10">{children}</div>
      </div>
    </section>
  );
}

function reducedMotion(): boolean {
  if (typeof window === "undefined") return true;
  return document.documentElement.dataset.reducedMotion === "true"
    || Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
}

/** True when the viewer asked for less motion (the OS setting, or the page's ?still switch). */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(reducedMotion);
  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!mq) return;
    const on = () => setReduced(reducedMotion());
    mq.addEventListener?.("change", on);
    return () => mq.removeEventListener?.("change", on);
  }, []);
  return reduced;
}

/**
 * Writes the element's scroll progress through the viewport to the CSS variable `--p` on it: 0 when its top is at
 * the bottom of the viewport, 1 when its top reaches `endAt` (a fraction of the viewport height). No re-renders; one
 * rAF per scroll. Under reduced motion it pins `--p` to `rest`.
 */
export function useScrollProgress<T extends HTMLElement>(endAt = 0.1, rest = 1): RefObject<T | null> {
  const ref = useRef<T>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (reducedMotion()) { el.style.setProperty("--p", String(rest)); return; }
    let frame = 0;
    const update = () => {
      frame = 0;
      const vh = window.innerHeight || 1;
      const top = el.getBoundingClientRect().top;
      const p = Math.min(1, Math.max(0, (vh - top) / (vh * (1 - endAt))));
      el.style.setProperty("--p", p.toFixed(3));
    };
    const on = () => { if (!frame) frame = requestAnimationFrame(update); };
    update();
    window.addEventListener("scroll", on, { passive: true });
    window.addEventListener("resize", on);
    return () => {
      window.removeEventListener("scroll", on);
      window.removeEventListener("resize", on);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [endAt, rest]);
  return ref;
}

/**
 * Lifts its children into place as they scroll into view. Content is always visible: only elements that start below
 * the fold are offset (never faded), and anything already on screen, or under reduced motion, is left exactly as is.
 */
export function Reveal({ children, className, delay = 0, as: Tag = "div" }: {
  children: ReactNode; className?: string; delay?: number; as?: "div" | "li";
}) {
  const ref = useRef<HTMLDivElement & HTMLLIElement>(null);
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || reducedMotion() || typeof IntersectionObserver === "undefined") return;
    if (el.getBoundingClientRect().top < window.innerHeight) return;
    setArmed(true);
    const io = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) { setArmed(false); io.disconnect(); }
    }, { rootMargin: "0px 0px -6% 0px", threshold: 0.01 });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return (
    <Tag ref={ref} className={cn("lp-reveal", armed && "is-armed", className)} style={{ transitionDelay: armed ? "0ms" : `${delay}ms` }}>
      {children}
    </Tag>
  );
}

/** A tablet with the real Herald screen on it. The caller tilts it (CSS transforms on a parent with perspective). */
export function Tablet({ shot, className, priority }: { shot: Shot; className?: string; priority?: boolean }) {
  return (
    <figure className={cn("lp-tablet", className)}>
      <span className="lp-tablet-cam" aria-hidden />
      <div className="lp-tablet-screen">
        <img src={shot.src} width={shot.width} height={shot.height} alt={shot.alt}
          className="block h-auto w-full" loading={priority ? "eager" : "lazy"} fetchPriority={priority ? "high" : "auto"} />
        <span className="lp-glare" aria-hidden />
      </div>
    </figure>
  );
}

/** A wall-mounted display (the ED board). */
export function Board({ shot, className, label }: { shot: Shot; className?: string; label?: string }) {
  return (
    <figure className={cn("lp-board", className)}>
      <div className="lp-board-screen">
        <img src={shot.src} width={shot.width} height={shot.height} alt={shot.alt} className="block h-auto w-full" loading="lazy" />
        <span className="lp-glare" aria-hidden />
      </div>
      {label && <figcaption className="lp-board-label">{label}</figcaption>}
    </figure>
  );
}
