// The middle of the page: the headline numbers, the problem, the ambulance-to-ED journey (a live packet flow between
// the medic tablet and the ED board) and the problem it solves.

import { Signal } from "lucide-react";
import { cn } from "@/lib/utils";
import { JOURNEY, PROBLEM_CLOSER, PROBLEMS, SHOTS, STATS } from "./content";
import { Board, Reveal, Section, Tablet, useReducedMotion, useScrollProgress } from "./primitives";

export function Stats() {
  return (
    <section aria-label="Measured results at a glance" className="relative z-[1] -mt-6 pb-4">
      <div className="lp-container">
        <ul className="lp-glass grid grid-cols-4 overflow-hidden rounded-[24px] max-lg:grid-cols-2 max-sm:grid-cols-1">
          {STATS.map((s, i) => (
            <Reveal as="li" key={s.label} delay={i * 70}
              className={cn("px-7 py-8 max-sm:px-6 max-sm:py-6", i > 0 && "border-[color:var(--glass-border)] lg:border-l",
                i % 2 === 1 && "sm:max-lg:border-l", i > 1 && "sm:max-lg:border-t", i > 0 && "max-sm:border-t")}>
              <p className="lp-stat-value num">{s.value}</p>
              <p className="mt-2.5 text-[1rem] font-semibold text-text-primary">{s.label}</p>
              <p className="mt-2 text-[.8125rem] leading-snug text-text-muted">{s.source}</p>
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
      lede="The medic treats the patient while tracking what's captured, what's changing, what's due and what still has to be asked. Then the whole story is handed over out loud, at the door.">
      <div className="grid grid-cols-3 gap-5 max-lg:grid-cols-1">
        {PROBLEMS.map((p, i) => (
          <Reveal key={p.label} delay={i * 80}>
            <figure className="lp-card h-full p-8">
              <p className="num text-[3rem] leading-none font-bold tracking-[-0.045em] text-text-primary max-sm:text-[2.5rem]">{p.value}</p>
              <figcaption>
                <p className="mt-4 text-[1.0625rem] leading-relaxed text-text-secondary">{p.label}</p>
                <p className="mt-6 border-t border-border-subtle pt-4 text-[.8125rem] text-text-muted">{p.source}</p>
              </figcaption>
            </figure>
          </Reveal>
        ))}
      </div>
      <Reveal delay={120}>
        <p className="mx-auto mt-16 max-w-[50rem] text-center text-[1.5rem] leading-snug font-semibold tracking-[-0.02em] text-balance text-text-primary max-sm:text-[1.25rem]">
          {PROBLEM_CLOSER}
        </p>
      </Reveal>
    </Section>
  );
}

// The arc between the two screens, in the SVG's own units (viewBox 0 0 400 260).
const ARC = "M8 196 Q200 -36 392 196";
const ARC_BACK = "M392 196 Q200 -36 8 196";
/** A point on the quadratic arc at t (0..1), for the still (reduced-motion) packets. */
function arcAt(t: number): [number, number] {
  const [x0, y0, cx, cy, x1, y1] = [8, 196, 200, -36, 392, 196];
  const u = 1 - t;
  return [u * u * x0 + 2 * u * t * cx + t * t * x1, u * u * y0 + 2 * u * t * cy + t * t * y1];
}

const PACKETS = [
  { tier: "critical", r: 7, begin: 0, cls: "lp-pk-critical" },
  { tier: "important", r: 5.5, begin: 0.55, cls: "lp-pk-important" },
  { tier: "context", r: 4.5, begin: 1.1, cls: "lp-pk-context" },
] as const;

/** Packets travelling the arc from the ambulance to the ED, and the ED's answer travelling back. */
function FlowArc() {
  const reduced = useReducedMotion();
  return (
    <svg className="lp-arc" viewBox="0 0 400 260" fill="none" aria-hidden>
      <defs>
        <linearGradient id="lp-arc-g" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" style={{ stopColor: "var(--accent)", stopOpacity: 0.15 }} />
          <stop offset=".5" style={{ stopColor: "var(--accent)", stopOpacity: 0.9 }} />
          <stop offset="1" style={{ stopColor: "var(--low-fg)", stopOpacity: 0.2 }} />
        </linearGradient>
        <filter id="lp-arc-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="3.5" />
        </filter>
      </defs>
      <path d={ARC} stroke="url(#lp-arc-g)" strokeWidth="2" strokeDasharray="2 7" strokeLinecap="round" />
      <path d={ARC} className="lp-arc-halo" strokeWidth="10" filter="url(#lp-arc-glow)" />
      {PACKETS.map((p, i) => {
        if (reduced) {
          const [x, y] = arcAt(0.62 - i * 0.14);
          return <circle key={p.tier} className={p.cls} cx={x} cy={y} r={p.r} />;
        }
        return (
          <g key={p.tier}>
            <circle className={p.cls} r={p.r + 6} opacity=".22" filter="url(#lp-arc-glow)">
              <animateMotion dur="3.2s" begin={`${p.begin}s`} repeatCount="indefinite" path={ARC} keyPoints="0;1" keyTimes="0;1" calcMode="spline" keySplines=".45 0 .55 1" />
            </circle>
            <circle className={p.cls} r={p.r}>
              <animateMotion dur="3.2s" begin={`${p.begin}s`} repeatCount="indefinite" path={ARC} keyPoints="0;1" keyTimes="0;1" calcMode="spline" keySplines=".45 0 .55 1" />
            </circle>
          </g>
        );
      })}
      {/* the ED's answer, back to the ambulance */}
      <g className="lp-ack" transform={reduced ? `translate(${arcAt(0.3).join(" ")})` : undefined}>
        {!reduced && <animateMotion dur="6.4s" begin="1.6s" repeatCount="indefinite" path={ARC_BACK} keyPoints="0;1" keyTimes="0;1" calcMode="spline" keySplines=".45 0 .55 1" />}
        <rect x="-66" y="-15" width="132" height="30" rx="15" />
        <text x="0" y="5" textAnchor="middle">Cath lab activated</text>
      </g>
    </svg>
  );
}

function LinkBadge() {
  return (
    <div className="lp-linkbadge">
      <span className="inline-flex items-center gap-2 font-semibold text-text-primary"><Signal size={15} className="text-medium-fg" aria-hidden /> Weak link · 50% loss</span>
      <span className="text-text-muted">critical first · 420-byte packets · <b className="font-semibold text-ok-fg">0 lost</b></span>
    </div>
  );
}

export function Journey() {
  const flow = useScrollProgress<HTMLDivElement>(0.35);
  return (
    <Section id="journey" eyebrow="How it works" title={<>From the back of the ambulance<br className="max-sm:hidden" /> to the ED, before the doors open</>}
      lede="The medic keeps working. Herald builds the record as the call is told, and the receiving team watches the patient arrive.">
      <div ref={flow} className="lp-flow">
        <div className="lp-flow-side lp-flow-left">
          <p className="lp-flow-cap"><span className="lp-flow-dot" /> In the ambulance · medic tablet</p>
          <div className="lp-flow-tilt lp-flow-tilt-l"><Tablet shot={SHOTS.medic} /></div>
        </div>
        <div className="lp-flow-mid">
          <FlowArc />
          <div className="lp-lane" aria-hidden><i /><i /><i /></div>
          <LinkBadge />
        </div>
        <div className="lp-flow-side lp-flow-right">
          <p className="lp-flow-cap"><span className="lp-flow-dot lp-flow-dot-ed" /> In the ED · incoming board</p>
          <div className="lp-flow-tilt lp-flow-tilt-r"><Board shot={SHOTS.edIncoming} /></div>
        </div>
      </div>

      <ol className="lp-steps">
        {JOURNEY.map((s, i) => (
          <Reveal as="li" key={s.title} delay={i * 90} className="lp-step">
            <span className="lp-step-num num">0{i + 1}</span>
            <p className="lp-step-time">{s.time}</p>
            <h3 className="mt-2 text-[1.1875rem] font-semibold tracking-[-0.02em]">{s.title}</h3>
            <p className="mt-2 text-[.9375rem] leading-relaxed text-text-secondary">{s.body}</p>
          </Reveal>
        ))}
      </ol>
    </Section>
  );
}
