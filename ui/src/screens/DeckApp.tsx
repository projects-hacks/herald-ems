// Herald pitch deck — interactive, self-contained presentation screen (Jenil, task D1–D3).
//
// Three required visuals live here: (1) an architecture diagram of the on-vehicle pipeline,
// (2) an interactive benchmark chart, and (3) an impact visual. Slides are keyboard-navigable
// (arrow keys / space) and reuse Herald's own design tokens so the deck looks native.
//
// NOTE ON NUMBERS: every figure is driven by the DECK_DATA object below and flagged with
// `placeholder: true` until real, model-locked benchmark results are dropped in. Nothing here
// invents a "final" number — swap the values in DECK_DATA when the model is locked.

import {
  Activity, ArrowLeft, ArrowRight, AudioLines, BrainCircuit, CheckCircle2, CloudOff,
  Hospital, ShieldCheck, Sparkles, TrendingDown, TrendingUp,
} from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

// ─────────────────────────────────────────────────────────────────────────────
// DATA — replace placeholder values with locked benchmark results before recording.
// ─────────────────────────────────────────────────────────────────────────────

const PLACEHOLDER = true; // flip to false once every figure below is a real, locked measurement.

type Bench = { label: string; value: number; unit: string; better: "lower" | "higher"; tint: string; fg: string };

const DECK_DATA = {
  title: "Herald",
  tagline: "On-vehicle AI that turns the ambulance conversation into a clean ER hand-off",
  sponsorTags: ["#SJSU", "#HeraldEMS", "#SponsorTag"], // TODO: real sponsor handles
  // Benchmark chart — local processing vs. a cloud round-trip baseline.
  benchmarks: [
    { label: "Local extraction latency", value: 1.8, unit: "s", better: "lower", tint: "bg-accent-tint", fg: "text-herald-accent" },
    { label: "Cloud round-trip baseline", value: 6.4, unit: "s", better: "lower", tint: "bg-medium-tint", fg: "text-medium-fg" },
    { label: "Fields auto-captured", value: 18, unit: "", better: "higher", tint: "bg-ok-tint", fg: "text-ok-fg" },
    { label: "Cloud AI calls", value: 0, unit: "", better: "lower", tint: "bg-low-tint", fg: "text-low-fg" },
  ] as Bench[],
  // Impact visual — before/after the ER receives Herald's structured hand-off.
  impact: [
    { label: "Pre-alert ready before arrival", before: 40, after: 92, unit: "%", dir: "up" as const },
    { label: "Info missing at hand-off", before: 55, after: 12, unit: "%", dir: "down" as const },
    { label: "Raw audio leaving the vehicle", before: 100, after: 0, unit: "%", dir: "down" as const },
  ],
};

// ─────────────────────────────────────────────────────────────────────────────
// Shared bits
// ─────────────────────────────────────────────────────────────────────────────

function PlaceholderTag() {
  if (!PLACEHOLDER) return null;
  return (
    <span className="rounded-full bg-medium-tint px-2.5 py-0.5 text-meta font-semibold text-medium-fg">
      placeholder data
    </span>
  );
}

function SlideFrame({ eyebrow, title, children }: { eyebrow: string; title: string; children: ReactNode }) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="mb-5 flex items-center gap-3">
        <span className="label-caps text-herald-accent">{eyebrow}</span>
        <PlaceholderTag />
      </div>
      <h2 className="mb-6 text-large-title font-bold tracking-display text-text-primary">{title}</h2>
      <div className="min-h-0 flex-1">{children}</div>
    </div>
  );
}

// ── Slide 1: Title ───────────────────────────────────────────────────────────
function TitleSlide() {
  return (
    <div className="flex h-full flex-col items-center justify-center text-center">
      <span className="mb-6 grid size-20 place-items-center rounded-full bg-accent-fill text-on-accent-fill">
        <AudioLines size={40} />
      </span>
      <h1 className="text-[3rem] font-bold tracking-display text-text-primary">{DECK_DATA.title}</h1>
      <p className="mt-4 max-w-2xl text-hero text-text-secondary">{DECK_DATA.tagline}</p>
      <div className="mt-8 flex flex-wrap justify-center gap-2">
        {DECK_DATA.sponsorTags.map((t) => (
          <span key={t} className="rounded-full bg-accent-tint px-3.5 py-1.5 text-body font-semibold text-herald-accent">{t}</span>
        ))}
      </div>
    </div>
  );
}

// ── Slide 2: Architecture diagram ──────────────────────────────────────────────
const ARCH_STAGES = [
  { icon: AudioLines, title: "Listen", detail: "Medic speaks naturally; mic streams on-device", tint: "bg-accent-tint", fg: "text-herald-accent" },
  { icon: BrainCircuit, title: "Structure", detail: "Local model turns speech into structured facts", tint: "bg-accent-tint", fg: "text-herald-accent" },
  { icon: ShieldCheck, title: "Human check", detail: "Anything uncertain waits for a medic's tap", tint: "bg-medium-tint", fg: "text-medium-fg" },
  { icon: Hospital, title: "ER relay", detail: "Only confirmed essentials leave the vehicle", tint: "bg-ok-tint", fg: "text-ok-fg" },
];

function ArchitectureSlide() {
  return (
    <SlideFrame eyebrow="Architecture" title="Everything runs on the vehicle">
      <div className="flex h-full flex-col justify-center">
        <div className="grid grid-cols-4 gap-3 max-lg:grid-cols-2">
          {ARCH_STAGES.map((st, i) => {
            const Icon = st.icon;
            return (
              <div key={st.title} className="relative flex flex-col">
                <div className="card flex h-full flex-col gap-3 p-5">
                  <span className={cn("grid size-12 place-items-center rounded-full", st.tint, st.fg)}>
                    <Icon size={24} />
                  </span>
                  <div>
                    <p className="text-meta font-bold text-text-muted">STEP {i + 1}</p>
                    <h3 className="text-title font-semibold text-text-primary">{st.title}</h3>
                    <p className="mt-1 text-body text-text-secondary">{st.detail}</p>
                  </div>
                </div>
                {i < ARCH_STAGES.length - 1 && (
                  <ArrowRight size={20} className="absolute top-1/2 -right-3 z-10 hidden -translate-y-1/2 text-text-muted lg:block" />
                )}
              </div>
            );
          })}
        </div>
        <div className="mt-6 flex items-center justify-center gap-2 rounded-[18px] bg-ok-tint px-5 py-3">
          <CloudOff size={18} className="text-ok-fg" />
          <p className="text-body font-semibold text-ok-fg">
            Raw audio, photos and uncertain facts never leave the ambulance
          </p>
        </div>
      </div>
    </SlideFrame>
  );
}

// ── Slide 3: Benchmark chart ────────────────────────────────────────────────────
function BenchmarkSlide() {
  const max = Math.max(...DECK_DATA.benchmarks.map((b) => b.value), 1);
  const [active, setActive] = useState<number | null>(null);
  return (
    <SlideFrame eyebrow="Benchmarks" title="Fast, local, and quiet on the network">
      <div className="flex h-full flex-col justify-center gap-4">
        {DECK_DATA.benchmarks.map((b, i) => {
          const pct = Math.max((b.value / max) * 100, 2);
          const Trend = b.better === "lower" ? TrendingDown : TrendingUp;
          return (
            <button
              key={b.label}
              type="button"
              onMouseEnter={() => setActive(i)}
              onFocus={() => setActive(i)}
              onMouseLeave={() => setActive(null)}
              onBlur={() => setActive(null)}
              className="hit group grid grid-cols-[240px_1fr_auto] items-center gap-4 rounded-[14px] p-2 text-left max-lg:grid-cols-1 max-lg:gap-1"
            >
              <span className="flex items-center gap-2 text-body font-medium text-text-secondary">
                <Trend size={15} className={b.fg} />{b.label}
              </span>
              <span className="h-8 overflow-hidden rounded-full bg-surface-2">
                <span
                  className={cn("block h-full rounded-full transition-[width] duration-500", b.tint, active === i && "opacity-80")}
                  style={{ width: `${pct}%` }}
                />
              </span>
              <strong className={cn("num min-w-16 text-right text-value font-bold", b.fg)}>
                {b.value}{b.unit}
              </strong>
            </button>
          );
        })}
        <p className="mt-2 flex items-center gap-2 text-meta text-text-muted">
          <Activity size={14} /> Lower is better for latency and cloud calls; higher is better for fields captured.
        </p>
      </div>
    </SlideFrame>
  );
}

// ── Slide 4: Impact visual ───────────────────────────────────────────────────────
function ImpactSlide() {
  return (
    <SlideFrame eyebrow="Impact" title="What changes for the ER">
      <div className="grid h-full grid-cols-3 items-stretch gap-4 max-lg:grid-cols-1">
        {DECK_DATA.impact.map((m) => {
          const good = m.dir === "up" ? m.after >= m.before : m.after <= m.before;
          const Trend = m.dir === "up" ? TrendingUp : TrendingDown;
          return (
            <div key={m.label} className="card flex flex-col justify-between gap-4 p-5">
              <p className="text-body font-medium text-text-secondary">{m.label}</p>
              <div className="flex items-end gap-3">
                <div className="flex flex-col">
                  <span className="text-meta text-text-muted">before</span>
                  <span className="num text-kpi font-bold text-text-muted line-through decoration-2">{m.before}{m.unit}</span>
                </div>
                <ArrowRight size={20} className="mb-2 text-text-muted" />
                <div className="flex flex-col">
                  <span className="text-meta text-text-muted">with Herald</span>
                  <span className={cn("num text-kpi font-bold", good ? "text-ok-fg" : "text-medium-fg")}>{m.after}{m.unit}</span>
                </div>
              </div>
              <span className={cn("inline-flex items-center gap-1.5 self-start rounded-full px-3 py-1 text-meta font-semibold",
                good ? "bg-ok-tint text-ok-fg" : "bg-medium-tint text-medium-fg")}>
                <Trend size={14} />{Math.abs(m.after - m.before)}{m.unit} {m.dir === "up" ? "gain" : "drop"}
              </span>
            </div>
          );
        })}
      </div>
    </SlideFrame>
  );
}

// ── Slide 5: Close ─────────────────────────────────────────────────────────────
function CloseSlide() {
  return (
    <div className="flex h-full flex-col items-center justify-center text-center">
      <span className="mb-6 grid size-16 place-items-center rounded-full bg-ok-tint text-ok-fg">
        <CheckCircle2 size={34} />
      </span>
      <h2 className="text-large-title font-bold tracking-display text-text-primary">Herald keeps the human in control</h2>
      <p className="mt-4 max-w-xl text-hero text-text-secondary">
        Local AI does the writing. The medic makes the call. The ER gets a clean, confirmed hand-off.
      </p>
      <div className="mt-8 flex flex-wrap justify-center gap-2">
        {DECK_DATA.sponsorTags.map((t) => (
          <span key={t} className="rounded-full bg-accent-tint px-3.5 py-1.5 text-body font-semibold text-herald-accent">{t}</span>
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Deck shell — keyboard + click navigation
// ─────────────────────────────────────────────────────────────────────────────

const SLIDES: { name: string; render: () => ReactNode }[] = [
  { name: "Title", render: () => <TitleSlide /> },
  { name: "Architecture", render: () => <ArchitectureSlide /> },
  { name: "Benchmarks", render: () => <BenchmarkSlide /> },
  { name: "Impact", render: () => <ImpactSlide /> },
  { name: "Close", render: () => <CloseSlide /> },
];

export function DeckApp() {
  const [i, setI] = useState(0);
  const go = useCallback((n: number) => setI((prev) => Math.min(Math.max(prev + n, 0), SLIDES.length - 1)), []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight" || e.key === " " || e.key === "PageDown") { e.preventDefault(); go(1); }
      else if (e.key === "ArrowLeft" || e.key === "PageUp") { e.preventDefault(); go(-1); }
      else if (e.key === "Home") setI(0);
      else if (e.key === "End") setI(SLIDES.length - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go]);

  return (
    <div className="flex h-dvh min-h-[640px] flex-col bg-canvas text-text-primary">
      <header className="flex min-h-16 shrink-0 items-center gap-3 border-b border-border-subtle bg-surface-1 px-7">
        <span className="grid size-9 place-items-center rounded-full bg-accent-fill text-on-accent-fill"><Sparkles size={17} /></span>
        <p className="text-title font-bold tracking-display">Herald · Pitch deck</p>
        <span className="num ml-auto text-meta font-semibold text-text-muted">{i + 1} / {SLIDES.length}</span>
      </header>

      <main className="mx-auto flex w-full max-w-[1200px] flex-1 flex-col overflow-y-auto px-8 py-8">
        {SLIDES[i].render()}
      </main>

      <footer className="flex min-h-16 shrink-0 items-center gap-3 border-t border-border-subtle bg-surface-1 px-7">
        <button type="button" onClick={() => go(-1)} disabled={i === 0}
          className="hit inline-flex h-10 items-center gap-2 rounded-full bg-surface-2 px-4 text-button font-semibold text-text-secondary hover:text-text-primary disabled:opacity-40">
          <ArrowLeft size={16} />Back
        </button>
        <div className="mx-auto flex items-center gap-1.5" role="tablist" aria-label="Slides">
          {SLIDES.map((s, n) => (
            <button key={s.name} type="button" onClick={() => setI(n)} aria-label={`Go to ${s.name}`} aria-selected={n === i} role="tab"
              className={cn("h-2 rounded-full transition-all", n === i ? "w-6 bg-herald-accent" : "w-2 bg-border-control hover:bg-text-muted")} />
          ))}
        </div>
        <button type="button" onClick={() => go(1)} disabled={i === SLIDES.length - 1}
          className="hit inline-flex h-10 items-center gap-2 rounded-full bg-accent-fill px-4 text-button font-semibold text-on-accent-fill hover:opacity-90 disabled:opacity-40">
          Next<ArrowRight size={16} />
        </button>
      </footer>
    </div>
  );
}
