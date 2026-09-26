// Measured results: the extractor comparison (one series, F1 on the held-out gold set) plus the supporting proofs.

import { BarChart3, Info, Table2 } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { EXTRACTORS, LIMITS, PROOFS, type Extractor } from "./content";
import { Reveal, Section } from "./primitives";

const TICKS = [0, 0.25, 0.5, 0.75, 1];

function Tooltip({ e }: { e: Extractor }) {
  const rows: [string, string][] = [
    ["Precision", e.precision.toFixed(2)], ["Recall", e.recall.toFixed(2)],
    ["Who said it", e.speaker.toFixed(2)], ["Latency p50 / p95", e.latency],
  ];
  return (
    <div role="tooltip" className="pointer-events-none absolute top-[calc(100%+6px)] right-0 z-20 w-60 rounded-[12px] border border-glass-border-hi bg-surface-3 p-3 shadow-[var(--shadow-2)]">
      <p className="text-[.8125rem] font-semibold text-text-primary">{e.name}</p>
      <dl className="mt-2 space-y-1">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-3 text-[.8125rem]">
            <dt className="text-text-muted">{k}</dt><dd className="num font-medium text-text-primary">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function F1Chart() {
  const [active, setActive] = useState<number | null>(null);
  return (
    <div className="relative">
      <div aria-hidden className="pointer-events-none absolute inset-y-0 right-[4.5rem] left-[13.5rem] max-sm:hidden">
        {TICKS.map((t) => (
          <span key={t} className="absolute inset-y-0 w-px bg-border-subtle" style={{ left: `${t * 100}%` }} />
        ))}
      </div>
      <ul className="relative space-y-2">
        {EXTRACTORS.map((e, i) => (
          <li key={e.name}>
            <button type="button" aria-describedby={active === i ? `f1-tip-${i}` : undefined}
              onMouseEnter={() => setActive(i)} onMouseLeave={() => setActive(null)} onFocus={() => setActive(i)} onBlur={() => setActive(null)}
              className="relative grid w-full grid-cols-[13.5rem_1fr_4.5rem] items-center rounded-[10px] py-2.5 text-left transition-colors hover:bg-surface-2/60 max-sm:grid-cols-[1fr_3.5rem] max-sm:gap-y-2">
              <span className="pr-4 pl-2 max-sm:col-span-2">
                <span className={cn("block text-[.9375rem] font-semibold", e.live ? "text-text-primary" : "text-text-secondary")}>{e.name}</span>
                <span className="block text-[.8125rem] text-text-muted">{e.detail}</span>
              </span>
              <span className="relative h-3">
                <span className={cn("absolute inset-y-0 left-0 rounded-r-[4px] transition-[width,opacity] duration-700",
                  e.live ? "bg-accent-fill shadow-[0_0_18px_-2px_var(--accent)]" : "bg-border-control/70", active !== null && active !== i && "opacity-50")}
                  style={{ width: `${e.f1 * 100}%` }} />
              </span>
              <span className={cn("num pr-2 text-right text-[1.0625rem] font-bold", e.live ? "text-text-primary" : "text-text-secondary")}>{e.f1.toFixed(3)}</span>
              {active === i && <span id={`f1-tip-${i}`}><Tooltip e={e} /></span>}
            </button>
          </li>
        ))}
      </ul>
      <div aria-hidden className="relative mt-1 h-5 text-[.75rem] text-text-muted max-sm:hidden">
        <div className="absolute inset-y-0 right-[4.5rem] left-[13.5rem]">
          {TICKS.map((t) => <span key={t} className="num absolute -translate-x-1/2" style={{ left: `${t * 100}%` }}>{t}</span>)}
        </div>
      </div>
    </div>
  );
}

function F1Table() {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[34rem] text-left text-[.875rem]">
        <caption className="sr-only">Speech-to-facts extractors on the held-out gold set</caption>
        <thead className="text-[.8125rem] text-text-muted">
          <tr className="border-b border-border-subtle">
            {["Extractor", "F1", "Precision", "Recall", "Who said it", "Latency p50 / p95"].map((h) => <th key={h} scope="col" className="px-2 py-2 font-medium">{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {EXTRACTORS.map((e) => (
            <tr key={e.name} className={cn("border-b border-border-subtle last:border-0", e.live && "font-semibold text-text-primary")}>
              <th scope="row" className="px-2 py-2.5 font-medium">{e.name} <span className="text-text-muted">· {e.detail}</span></th>
              <td className="num px-2">{e.f1.toFixed(3)}</td><td className="num px-2">{e.precision.toFixed(2)}</td>
              <td className="num px-2">{e.recall.toFixed(2)}</td><td className="num px-2">{e.speaker.toFixed(2)}</td>
              <td className="num px-2 whitespace-nowrap">{e.latency}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Results() {
  const [view, setView] = useState<"chart" | "table">("chart");
  return (
    <Section id="results" eyebrow="Measured, not promised" title="Fine-tuned on the box. Tested on data it never saw."
      lede="A held-out gold set of 100 utterances and 320 facts, labeled by two annotators who never saw the models or the training data. Three runs each.">
      <div className="grid grid-cols-[1.45fr_1fr] gap-4 max-lg:grid-cols-1">
        <Reveal>
          <div className="lp-card h-full p-6 max-sm:p-4">
            <div className="flex flex-wrap items-center gap-3">
              <div>
                <h3 className="text-[1.0625rem] font-semibold">Speech-to-facts F1</h3>
                <p className="text-[.8125rem] text-text-muted">Hover a bar for precision, recall and latency</p>
              </div>
              <div role="group" aria-label="View" className="ml-auto inline-flex rounded-full border border-border-subtle bg-bg/60 p-1">
                {([["chart", BarChart3], ["table", Table2]] as const).map(([v, Icon]) => (
                  <button key={v} type="button" aria-pressed={view === v} onClick={() => setView(v)}
                    className={cn("inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-[.8125rem] font-semibold capitalize transition-colors",
                      view === v ? "bg-surface-3 text-text-primary" : "text-text-muted hover:text-text-secondary")}>
                    <Icon size={14} aria-hidden /> {v}
                  </button>
                ))}
              </div>
            </div>
            <div className="mt-6">{view === "chart" ? <F1Chart /> : <F1Table />}</div>
          </div>
        </Reveal>
        <div className="grid grid-cols-2 gap-4 max-sm:grid-cols-1">
          {PROOFS.map((p, i) => (
            <Reveal key={p.label} delay={i * 70}>
              <div className="lp-card h-full p-5">
                <p className="num text-[1.625rem] leading-tight font-bold tracking-[-0.03em] text-text-primary">{p.value}</p>
                <p className="mt-2 text-[.875rem] leading-relaxed text-text-secondary">{p.label}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
      <Reveal delay={100}>
        <div className="mt-4 flex items-start gap-3 rounded-[16px] border border-border-subtle bg-surface-1/60 p-4 text-[.875rem] leading-relaxed text-text-secondary">
          <Info size={18} className="mt-0.5 shrink-0 text-low-fg" aria-hidden />
          <p><span className="font-semibold text-text-primary">Honest limits. </span>{LIMITS}</p>
        </div>
      </Reveal>
    </Section>
  );
}
