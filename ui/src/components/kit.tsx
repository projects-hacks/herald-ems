// The visual kit every page is built from: cards and their headers, sections inside a card, badges, counts, icon
// badges, buttons, progress, empty states and page headers. One place for the look, so every page stays consistent.
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export type Tone = "neutral" | "accent" | "ok" | "medium" | "high" | "low";

export const TINT: Record<Tone, string> = {
  neutral: "bg-surface-2 text-text-secondary",
  accent: "bg-accent-tint text-herald-accent",
  ok: "bg-ok-tint text-ok-fg",
  medium: "bg-medium-tint text-medium-fg",
  high: "bg-high-tint text-high-fg",
  low: "bg-low-tint text-low-fg",
};
export const TEXT: Record<Tone, string> = {
  neutral: "text-text-secondary", accent: "text-herald-accent", ok: "text-ok-fg", medium: "text-medium-fg", high: "text-high-fg", low: "text-low-fg",
};
export const DOT: Record<Tone, string> = {
  neutral: "bg-text-muted", accent: "bg-herald-accent", ok: "bg-ok-fg", medium: "bg-medium-fg", high: "bg-high-fg", low: "bg-low-fg",
};
const SOLID: Record<Tone, string> = {
  neutral: "bg-text-secondary text-bg", accent: "bg-accent-fill text-on-accent-fill", ok: "bg-ok-fill text-ok-on-fill",
  medium: "bg-medium-fill text-medium-on-fill border border-medium-fill-border", high: "bg-high-fill text-high-on-fill", low: "bg-low-fill text-low-on-fill",
};

// ---------- containers ----------

export function Card({ className, ...rest }: React.ComponentProps<"section">) {
  return <section className={cn("card flex min-h-0 flex-col", className)} {...rest} />;
}

/** Title row of a card: icon badge, title with an optional badge, a one-line subtitle, actions on the right. */
export function CardHeader({ icon, tone = "accent", title, subtitle, id, badge, actions, className }: {
  icon?: LucideIcon; tone?: Tone; title: React.ReactNode; subtitle?: React.ReactNode; id?: string;
  badge?: React.ReactNode; actions?: React.ReactNode; className?: string;
}) {
  return (
    <header className={cn("flex shrink-0 items-center gap-3 px-5 pt-4 pb-3", className)}>
      {icon && <IconBadge icon={icon} tone={tone} />}
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-center gap-2">
          <h2 id={id} className="truncate text-title font-semibold text-text-primary">{title}</h2>
          {badge}
        </div>
        {subtitle && <p className="truncate text-meta text-text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  );
}

/** A labelled group inside a card, e.g. "Choose a value · 1". */
export function Section({ title, count, tone = "neutral", actions, children, className }: {
  title: string; count?: number; tone?: Tone; actions?: React.ReactNode; children: React.ReactNode; className?: string;
}) {
  return (
    <section className={cn("flex flex-col", className)} aria-label={title}>
      <div className="flex min-h-9 items-center gap-2 px-5 pt-2">
        <h3 className="label-caps text-text-muted">{title}</h3>
        {count !== undefined && <Count n={count} tone={tone} />}
        {actions && <span className="ml-auto">{actions}</span>}
      </div>
      {children}
    </section>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="min-w-0 flex-1">
        <h1 className="text-[1.375rem] leading-8 font-semibold tracking-display">{title}</h1>
        {description && <p className="text-body text-text-muted">{description}</p>}
      </div>
      {actions}
    </div>
  );
}

export function EmptyState({ icon: Icon, tone = "ok", title, children, className }: {
  icon: LucideIcon; tone?: Tone; title: string; children?: React.ReactNode; className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-2 px-6 py-8 text-center", className)}>
      <span className={cn("grid size-12 place-items-center rounded-full", TINT[tone])} aria-hidden><Icon size={24} strokeWidth={2.2} /></span>
      <p className="text-critical font-semibold">{title}</p>
      {children && <div className="max-w-sm text-body text-text-muted">{children}</div>}
    </div>
  );
}

// ---------- small pieces ----------

export function IconBadge({ icon: Icon, tone = "accent", size = 36, className, iconClassName }: {
  icon: LucideIcon; tone?: Tone; size?: number; className?: string; iconClassName?: string;
}) {
  return (
    <span className={cn("grid shrink-0 place-items-center rounded-[10px]", TINT[tone], className)} style={{ width: size, height: size }} aria-hidden>
      <Icon size={Math.round(size * 0.5)} strokeWidth={2.2} className={iconClassName} />
    </span>
  );
}

/** Status badge: soft (tinted, the default), solid (the one thing that must stand out) or outline (quiet). */
export function Badge({ tone = "neutral", variant = "soft", icon: Icon, dot = false, children, className }: {
  tone?: Tone; variant?: "soft" | "solid" | "outline"; icon?: LucideIcon; dot?: boolean; children: React.ReactNode; className?: string;
}) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-meta font-semibold",
      variant === "solid" ? SOLID[tone] : variant === "outline" ? cn("border border-border-subtle", TEXT[tone]) : TINT[tone], className)}>
      {dot && <span className={cn("size-1.5 shrink-0 rounded-full", DOT[tone])} aria-hidden />}
      {Icon && <Icon size={13} strokeWidth={2.5} aria-hidden className="shrink-0" />}
      {children}
    </span>
  );
}

export function Count({ n, tone = "neutral", className }: { n: number | string; tone?: Tone; className?: string }) {
  return <span className={cn("num inline-grid min-w-6 place-items-center rounded-full px-1.5 text-meta leading-5 font-semibold", TINT[tone], className)}>{n}</span>;
}

export function Dot({ tone, className }: { tone: Tone; className?: string }) {
  return <span className={cn("inline-block size-2 shrink-0 rounded-full", DOT[tone], className)} aria-hidden />;
}

export function Button({ variant = "secondary", size = "md", className, ...rest }: React.ComponentProps<"button"> & {
  variant?: "primary" | "secondary" | "ghost"; size?: "sm" | "md" | "lg";
}) {
  return (
    <button type="button" {...rest} className={cn(
      "hit inline-flex shrink-0 items-center justify-center gap-2 rounded-[var(--radius-control)] font-semibold whitespace-nowrap transition-[background-color,filter,color] duration-[var(--dur-short3)] disabled:cursor-not-allowed disabled:opacity-50",
      size === "sm" && "h-9 px-3 text-meta", size === "md" && "h-10 px-4 text-button", size === "lg" && "h-11 px-5 text-button",
      variant === "primary" && "bg-accent-fill text-on-accent-fill shadow-[var(--shadow-1)] enabled:hover:brightness-110",
      variant === "secondary" && "border border-border-subtle bg-surface-2 text-text-primary enabled:hover:bg-surface-3",
      variant === "ghost" && "text-text-secondary enabled:hover:bg-surface-2 enabled:hover:text-text-primary",
      className)} />
  );
}

/** One bar per checklist item, colored by state (done / needs a tap / missing). */
export function SegmentBar({ states, className }: { states: ("done" | "pending" | "missing")[]; className?: string }) {
  return (
    <span className={cn("flex h-2 w-full gap-1", className)} aria-hidden>
      {states.map((st, i) => (
        <span key={i} className={cn("h-full flex-1 rounded-full",
          st === "done" ? "bg-ok-fg" : st === "pending" ? "hatch" : "bg-surface-2 ring-1 ring-inset ring-border-control/60")} />
      ))}
    </span>
  );
}

export function ProgressBar({ frac, tone = "accent", className }: { frac: number; tone?: Tone; className?: string }) {
  return (
    <span className={cn("block h-1.5 w-full overflow-hidden rounded-full bg-surface-2", className)} aria-hidden>
      <span className={cn("block h-full rounded-full", DOT[tone])} style={{ width: `${Math.round(Math.max(0, Math.min(1, frac)) * 100)}%` }} />
    </span>
  );
}
