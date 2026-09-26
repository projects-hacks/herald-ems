// Measured results: one comparison (a prompted 30B model against our fine-tuned 4B model, F1 on the held-out gold
// set), the supporting proofs, and the stack of models running on the box.

import { Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { COMPARISON, PROOFS, STACK } from "./content";
import { Reveal, Section, useScrollProgress } from "./primitives";

function Comparison() {
  const bars = useScrollProgress<HTMLDivElement>(0.45);
  const ours = COMPARISON.find((c) => c.ours)!;
  const base = COMPARISON.find((c) => !c.ours)!;
  const gain = Math.round((ours.f1 / base.f1 - 1) * 100);
  return (
    <div ref={bars} className="lp-card lp-compare h-full p-8 max-sm:p-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h3 className="text-[1.25rem] font-semibold tracking-[-0.02em]">Speech → facts, F1</h3>
          <p className="mt-1 text-[.875rem] text-text-muted">Held-out gold set · 100 utterances · 320 facts · 3 runs each</p>
        </div>
        <span className="lp-gain"><Sparkles size={15} aria-hidden /> +{gain}% F1 with 7× fewer parameters</span>
      </div>
      <ul className="mt-8 space-y-7">
        {COMPARISON.map((c) => (
          <li key={c.name}>
            <div className="flex items-baseline justify-between gap-4">
              <span>
                <span className={cn("block text-[1.0625rem] font-semibold", c.ours ? "text-text-primary" : "text-text-secondary")}>{c.name}</span>
                <span className="block text-[.8125rem] text-text-muted">{c.detail}</span>
              </span>
              <span className={cn("num text-[2.5rem] leading-none font-bold tracking-[-0.04em] max-sm:text-[2rem]", c.ours ? "lp-gradient-text" : "text-text-secondary")}>{c.f1.toFixed(3)}</span>
            </div>
            <div className="lp-bar mt-3">
              <span className={cn("lp-bar-fill", c.ours ? "is-ours" : "is-base")} style={{ ["--w" as string]: String(c.f1) }} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Results() {
  return (
    <Section id="results" eyebrow="Measured, not promised" title="A 4B model we fine-tuned beats a prompted 30B model"
      lede="Tested on a held-out gold set the models never saw, labeled by two independent annotators, three runs each.">
      <div className="grid grid-cols-[1.35fr_1fr] gap-5 max-lg:grid-cols-1">
        <Reveal><Comparison /></Reveal>
        <div className="grid grid-cols-2 gap-5 max-sm:grid-cols-1">
          {PROOFS.map((p, i) => (
            <Reveal key={p.label} delay={i * 70}>
              <div className="lp-card h-full p-6">
                <p className="num text-[2rem] leading-tight font-bold tracking-[-0.035em] text-text-primary">{p.value}</p>
                <p className="mt-2 text-[.875rem] leading-relaxed text-text-secondary">{p.label}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>

      <Reveal delay={60}>
        <div id="stack" className="lp-stack mt-5">
          <div className="lp-stack-head">
            <div>
              <p className="lp-eyebrow">The model stack · all on one box</p>
              <p className="mt-2 text-[1.75rem] leading-tight font-bold tracking-[-0.03em]">Two models fine-tuned on this box</p>
            </div>
            <p className="max-w-[30rem] text-[.9375rem] leading-relaxed text-text-secondary">Four local models, one HP ZGX Nano. The two that do the thinking were fine-tuned right here, on the GB10.</p>
          </div>
          <ul className="lp-stack-grid">
            {STACK.map((s) => (
              <li key={s.model} className={cn("lp-stack-item", s.tuned && "is-tuned")}>
                {s.tuned ? <span className="lp-tag lp-tag-accent">Fine-tuned here</span> : <span className="lp-tag">Local</span>}
                <p className="mt-4 text-[.8125rem] font-semibold text-text-muted">{s.job}</p>
                <p className="mt-1 text-[1.1875rem] font-bold tracking-[-0.02em]">{s.model}</p>
                <p className="mt-1.5 text-[.875rem] leading-relaxed text-text-secondary">{s.detail}</p>
              </li>
            ))}
          </ul>
        </div>
      </Reveal>
    </Section>
  );
}
