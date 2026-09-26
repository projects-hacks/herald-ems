// Small building blocks shared by the landing sections: the brand mark, section frame, eyebrow and scroll reveal.

import { Activity } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5 text-[1.2rem] font-[750] tracking-[-0.055em] text-text-primary", className)}>
      <span className="grid size-9 place-items-center rounded-[11px] bg-accent-fill text-on-accent-fill shadow-[0_0_24px_-4px_var(--accent)]">
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
        <Reveal className="mx-auto max-w-[44rem] text-center">
          <Eyebrow>{eyebrow}</Eyebrow>
          <h2 id={id ? `${id}-title` : undefined} className="lp-h2">{title}</h2>
          {lede && <p className="lp-lede mx-auto mt-4">{lede}</p>}
        </Reveal>
        <div className="mt-14 max-sm:mt-10">{children}</div>
      </div>
    </section>
  );
}

/** Fades its children up once they scroll into view. Reduced motion (or no IntersectionObserver): shown at once. */
export function Reveal({ children, className, delay = 0, as: Tag = "div" }: {
  children: ReactNode; className?: string; delay?: number; as?: "div" | "li";
}) {
  const ref = useRef<HTMLDivElement & HTMLLIElement>(null);
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches || document.documentElement.dataset.reducedMotion === "true";
    const onScreen = el.getBoundingClientRect().top < window.innerHeight;
    if (reduced || onScreen || typeof IntersectionObserver === "undefined") { setShown(true); return; }
    const io = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) { setShown(true); io.disconnect(); }
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return (
    <Tag ref={ref} className={cn("lp-reveal", shown && "is-shown", className)} style={{ transitionDelay: `${delay}ms` }}>
      {children}
    </Tag>
  );
}
