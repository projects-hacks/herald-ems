// Icon + word + color for every state in UX_PLAN §2.4: meaning never depends on color alone (P6).
import {
  CircleCheck, CircleDashed, CircleQuestionMark, CircleSlash, CircleX, GitCompareArrows, Hourglass, Info, Lock,
  OctagonAlert, Signal, SignalLow, SignalZero, TriangleAlert, Wifi, WifiOff, type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

export type StatusKind =
  | "high" | "medium" | "contradiction" | "low" | "done" | "tap" | "missing" | "rejected" | "queued" | "held"
  | "link-good" | "link-weak" | "link-down" | "link-unknown" | "link-off";

const MAP: Record<StatusKind, { icon: LucideIcon; word: string; tone: string }> = {
  high: { icon: OctagonAlert, word: "HIGH", tone: "text-high-fg" },
  medium: { icon: TriangleAlert, word: "CHECK", tone: "text-medium-fg" },
  contradiction: { icon: GitCompareArrows, word: "CHECK", tone: "text-medium-fg" },
  low: { icon: Info, word: "", tone: "text-low-fg" },
  done: { icon: CircleCheck, word: "Done", tone: "text-ok-fg" },
  tap: { icon: CircleQuestionMark, word: "Needs your tap", tone: "text-text-primary" },
  missing: { icon: CircleDashed, word: "Missing", tone: "text-text-muted" },
  rejected: { icon: CircleX, word: "Rejected", tone: "text-text-muted" },
  queued: { icon: Hourglass, word: "Queued", tone: "text-low-fg" },
  held: { icon: Lock, word: "Held", tone: "text-text-secondary" },
  "link-good": { icon: Wifi, word: "Good", tone: "text-ok-fg" },
  "link-weak": { icon: SignalLow, word: "Weak", tone: "text-low-fg" },
  "link-down": { icon: WifiOff, word: "Offline", tone: "text-low-fg" },
  "link-unknown": { icon: SignalZero, word: "Checking", tone: "text-low-fg" },
  "link-off": { icon: CircleSlash, word: "Not set up", tone: "text-text-muted" },
};

export function StatusIcon({ kind, word, size = 20, className, hideWord = false }: {
  kind: StatusKind; word?: string; size?: number; className?: string; hideWord?: boolean;
}) {
  const m = MAP[kind];
  const Icon = m.icon;
  const text = word ?? m.word;
  return (
    <span className={cn("inline-flex items-center gap-1.5", m.tone, className)}>
      <Icon size={size} aria-hidden={!hideWord ? true : undefined} aria-label={hideWord ? text : undefined} className="shrink-0" />
      {!hideWord && text && <span>{text}</span>}
    </span>
  );
}
export { Signal };
