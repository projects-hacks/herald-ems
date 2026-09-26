// The visual kit every page is built from, in the Apple Health idiom: plain cards on a grouped background; a card
// title in its category's color with a small glyph; values as a big rounded number with a small gray unit; rounded-
// square icon tiles with white glyphs (as in the iPad sidebar and Settings); inset-grouped lists with hairlines;
// iOS buttons (filled, gray, plain); capsule badges; a ring for progress. One place for the look.
import { Brain, Camera, CircleCheck, Clock, HeartPulse, Inbox, Keyboard, Mic, Monitor, Pill, Send, TriangleAlert, UserRound, type LucideIcon } from "lucide-react";
import type { Cat } from "@/lib/categories";
import { cn } from "@/lib/utils";

export type { Cat };

// ---------- color vocabularies ----------

/** Status tones: they carry meaning, always with an icon or a word. */
export type Tone = "neutral" | "accent" | "ok" | "medium" | "high" | "low";
/** Each category's glyph, for tiles and titles. */
export const CAT_ICON: Record<Cat, LucideIcon> = {
  attention: Inbox, time: Clock, heart: HeartPulse, neuro: Brain, ed: Send, check: CircleCheck, meds: Pill, patient: UserRound, speech: Mic,
};

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
export const CAT_FG: Record<Cat, string> = {
  attention: "text-cat-attention-fg", time: "text-cat-time-fg", heart: "text-cat-heart-fg", neuro: "text-cat-neuro-fg",
  ed: "text-cat-ed-fg", check: "text-cat-check-fg", meds: "text-cat-meds-fg", patient: "text-cat-patient-fg", speech: "text-cat-speech-fg",
};
const CAT_BG: Record<Cat, string> = {
  attention: "bg-cat-attention", time: "bg-cat-time", heart: "bg-cat-heart", neuro: "bg-cat-neuro",
  ed: "bg-cat-ed", check: "bg-cat-check", meds: "bg-cat-meds", patient: "bg-cat-patient", speech: "bg-cat-speech",
};
export const CAT_STROKE: Record<Cat, string> = {
  attention: "var(--cat-attention-fg)", time: "var(--cat-time-fg)", heart: "var(--cat-heart-fg)", neuro: "var(--cat-neuro-fg)",
  ed: "var(--cat-ed-fg)", check: "var(--cat-check-fg)", meds: "var(--cat-meds-fg)", patient: "var(--cat-patient-fg)", speech: "var(--cat-speech-fg)",
};

// ---------- containers ----------

export function Card({ className, ...rest }: React.ComponentProps<"section">) {
  return <section className={cn("card flex min-h-0 flex-col", className)} {...rest} />;
}

/** A Health card's title row: the category glyph and title in the category color, then a badge; on the right, quiet
 *  details (a time, a count) or actions. An optional gray subtitle sits under the title. */
export function CardHeader({ icon: Icon, cat, title, subtitle, id, badge, actions, className }: {
  icon?: LucideIcon; cat?: Cat; title: React.ReactNode; subtitle?: React.ReactNode; id?: string;
  badge?: React.ReactNode; actions?: React.ReactNode; className?: string;
}) {
  return (
    <header className={cn("flex shrink-0 items-start gap-3 px-5 pt-4 pb-3", className)}>
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-center gap-2">
          {Icon && <Icon size={18} strokeWidth={2.4} aria-hidden className={cn("shrink-0", cat ? CAT_FG[cat] : "text-text-muted")} />}
          <h2 id={id} className={cn("truncate text-title font-semibold", cat ? CAT_FG[cat] : "text-text-primary")}>{title}</h2>
          {badge}
        </div>
        {subtitle && <p className="mt-0.5 text-meta text-text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2 text-meta text-text-muted">{actions}</div>}
    </header>
  );
}

/** An iOS grouped-list section label inside a card: small caps, gray. */
export function Section({ title, count, actions, children, className }: {
  title: string; count?: number; tone?: Tone; actions?: React.ReactNode; children: React.ReactNode; className?: string;
}) {
  return (
    <section className={cn("flex flex-col", className)} aria-label={title}>
      <div className="flex min-h-9 items-end gap-2 px-5 pb-1.5">
        <h3 className="label-caps text-text-muted">{title}{count !== undefined && <span className="num"> · {count}</span>}</h3>
        {actions && <span className="ml-auto">{actions}</span>}
      </div>
      {children}
    </section>
  );
}

/** A page's large title (iOS "Summary"), with a gray line under it. */
export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="min-w-0 flex-1">
        <h1 className="text-large-title font-bold tracking-display">{title}</h1>
        {description && <p className="text-body text-text-muted">{description}</p>}
      </div>
      {actions}
    </div>
  );
}

export function EmptyState({ icon: Icon, cat = "check", title, children, className }: {
  icon: LucideIcon; cat?: Cat; title: string; children?: React.ReactNode; className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-2 px-6 py-8 text-center", className)}>
      <IconTile icon={Icon} cat={cat} size={44} />
      <p className="mt-1 text-critical font-semibold">{title}</p>
      {children && <div className="max-w-sm text-body text-text-muted">{children}</div>}
    </div>
  );
}

// ---------- small pieces ----------

/** A rounded-square tile in the category's tint with the glyph in the category's foreground: the pair is defined for
 *  both themes (styles/tokens.css), where a white glyph vanished on the light theme's pale tints. */
export function IconTile({ icon: Icon, cat, size = 32, className, iconClassName }: {
  icon: LucideIcon; cat: Cat; size?: number; className?: string; iconClassName?: string;
}) {
  return (
    <span className={cn("grid shrink-0 place-items-center rounded-[var(--radius-tile)]", CAT_BG[cat], CAT_FG[cat], className)}
      style={{ width: size, height: size, borderRadius: Math.round(size * 0.26) }} aria-hidden>
      <Icon size={Math.round(size * 0.56)} strokeWidth={2.4} className={iconClassName} />
    </span>
  );
}

/** A value the Health way: a big rounded number and a small gray unit. */
export function Value({ value, unit, size = "kpi", muted, severity, className }: {
  value: React.ReactNode; unit?: React.ReactNode; size?: "kpi" | "clock" | "value"; muted?: boolean;
  severity?: "abnormal" | "critical"; className?: string;
}) {
  // A clinical severity (config/vital_ranges.yaml, backend-computed) colours the number AND adds a word+icon badge,
  // so an out-of-range value is never distinguished by colour alone (IEC 60601-1-8 / WCAG: colour + text + shape).
  const sev = severity ? SEVERITY[severity] : null;
  return (
    <span className={cn("inline-flex min-w-0 items-baseline gap-1.5", className)}>
      <span className={cn("rounded-num truncate", size === "kpi" ? "text-kpi" : size === "clock" ? "text-clock" : "text-value",
        sev ? TEXT[sev.tone] : muted && "text-text-muted")}>{value}</span>
      {unit && <span className="shrink-0 text-body font-semibold text-text-muted">{unit}</span>}
      {sev && <SeverityBadge severity={severity!} />}
    </span>
  );
}

/** Clinical severity -> a priority tone and the word a medic reads. Critical is the danger red, abnormal the amber
 *  "needs you". One place, so a tile, a list row and a badge always say the same thing. */
export const SEVERITY: Record<"abnormal" | "critical", { tone: Tone; word: string }> = {
  abnormal: { tone: "medium", word: "out of range" },
  critical: { tone: "high", word: "critical" },
};

/** The badge that must accompany any severity colour, so the value is never distinguished by colour alone. */
export function SeverityBadge({ severity, className }: { severity: "abnormal" | "critical"; className?: string }) {
  const s = SEVERITY[severity];
  return <Badge tone={s.tone} icon={TriangleAlert} className={className}>{s.word}</Badge>;
}

/** Where a value came from, as a small labelled glyph: camera (a photo), monitor (a device feed), voice, or typed.
 *  Shown wherever a value appears, not only in the full Facts tab, so a photo-read vital is never mistaken for a
 *  spoken one on the tiles. `aria-label` carries the word for screen readers. */
export function SourceIcon({ capturedBy, role, hasAudio, className }: {
  capturedBy: "medic" | "other" | "device" | "camera"; role?: string; hasAudio?: boolean; className?: string;
}) {
  // device (a monitor feed) or the camera reading the patient monitor (role "device") -> the monitor, any other
  // camera read -> a photo, an audio clip -> spoken, otherwise typed. A spoken value is captured_by "medic"/"other"
  // with an audio_id, not a distinct source value, so voice is keyed off hasAudio.
  const [Icon, label] = capturedBy === "device" || (capturedBy === "camera" && role === "device") ? [Monitor, "monitor"]
    : capturedBy === "camera" ? [Camera, "photo"]
    : hasAudio ? [Mic, "voice"] : [Keyboard, "typed"];
  return <Icon size={13} aria-label={label} className={cn("shrink-0 text-text-muted", className)} />;
}

/** Capsule badge: soft (tinted, the default), solid (the one thing that must stand out) or outline (quiet). */
export function Badge({ tone = "neutral", variant = "soft", icon: Icon, dot = false, children, className }: {
  tone?: Tone; variant?: "soft" | "solid" | "outline"; icon?: LucideIcon; dot?: boolean; children: React.ReactNode; className?: string;
}) {
  return (
    <span className={cn("inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-meta font-semibold",
      variant === "solid" ? SOLID[tone] : variant === "outline" ? cn("border border-border-subtle", TEXT[tone]) : TINT[tone], className)}>
      {dot && <span className={cn("size-1.5 shrink-0 rounded-full", DOT[tone])} aria-hidden />}
      {Icon && <Icon size={13} strokeWidth={2.6} aria-hidden className="shrink-0" />}
      {children}
    </span>
  );
}

/** A count: gray text like iOS list counts; a red capsule when something is urgent. */
export function Count({ n, tone = "neutral", className }: { n: number | string; tone?: Tone; className?: string }) {
  return tone === "high"
    ? <span className={cn("num inline-grid min-w-6 place-items-center rounded-full bg-high-fill px-1.5 text-meta leading-5 font-bold text-high-on-fill", className)}>{n}</span>
    : <span className={cn("num text-body font-medium text-text-muted", className)}>{n}</span>;
}

export function Dot({ tone, className }: { tone: Tone; className?: string }) {
  return <span className={cn("inline-block size-2 shrink-0 rounded-full", DOT[tone], className)} aria-hidden />;
}

/** iOS buttons: filled (the one primary action), gray (secondary), plain (blue text). */
export function Button({ variant = "secondary", size = "md", className, ...rest }: React.ComponentProps<"button"> & {
  variant?: "primary" | "secondary" | "ghost"; size?: "sm" | "md" | "lg";
}) {
  return (
    <button type="button" {...rest} className={cn(
      "hit inline-flex shrink-0 items-center justify-center gap-1.5 rounded-[var(--radius-control)] font-semibold whitespace-nowrap transition-[background-color,filter,color,opacity] duration-[var(--dur-short3)] disabled:cursor-not-allowed disabled:opacity-45",
      size === "sm" && "min-h-12 px-3 text-meta", size === "md" && "min-h-12 px-4 text-button", size === "lg" && "min-h-12 px-5 text-button",
      variant === "primary" && "min-h-16 bg-accent-fill text-on-accent-fill enabled:hover:brightness-110 enabled:active:brightness-95",
      variant === "secondary" && "bg-surface-2 text-text-primary enabled:hover:bg-surface-3",
      variant === "ghost" && "text-herald-accent enabled:hover:bg-accent-tint",
      className)} />
  );
}

/** A progress ring in the category color, Activity-ring style: a dim track and a rounded bright arc. */
export function Ring({ done, total, cat = "check", size = 76, stroke = 10, children, label }: {
  done: number; total: number; cat?: Cat; size?: number; stroke?: number; children?: React.ReactNode; label: string;
}) {
  const r = (size - stroke) / 2, c = 2 * Math.PI * r;
  const frac = total ? Math.min(1, done / total) : 0;
  const color = CAT_STROKE[cat];
  return (
    <span className="relative inline-grid shrink-0 place-items-center" style={{ width: size, height: size }} role="img" aria-label={label}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeOpacity={0.2} strokeWidth={stroke} />
        {frac > 0 && <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - frac)} className="transition-[stroke-dashoffset] duration-[var(--dur-medium1)]" />}
      </svg>
      <span className="absolute inset-0 grid place-items-center">{children}</span>
    </span>
  );
}

/** One bar per checklist item, colored by state (done / needs a tap / missing). */
export function SegmentBar({ states, className }: { states: ("done" | "pending" | "missing")[]; className?: string }) {
  return (
    <span className={cn("flex h-1.5 w-full gap-1", className)} aria-hidden>
      {states.map((st, i) => (
        <span key={i} className={cn("h-full flex-1 rounded-full", st === "done" ? "bg-cat-check" : st === "pending" ? "hatch" : "bg-surface-3")} />
      ))}
    </span>
  );
}

export function ProgressBar({ frac, cat, tone = "accent", className }: { frac: number; cat?: Cat; tone?: Tone; className?: string }) {
  return (
    <span className={cn("block h-1.5 w-full overflow-hidden rounded-full bg-surface-3", className)} aria-hidden>
      <span className={cn("block h-full rounded-full", !cat && DOT[tone])}
        style={{ width: `${Math.round(Math.max(0, Math.min(1, frac)) * 100)}%`, background: cat ? CAT_STROKE[cat] : undefined }} />
    </span>
  );
}
