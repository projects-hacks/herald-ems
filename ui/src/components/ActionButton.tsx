// A clinical action: pressed and disabled within 0.1 s, "Still waiting…" after 2 s, an inline error in words on
// failure (UX_PLAN §3.0), and off in a replay. Buttons are 44 px with a 52 px hit area (plan: 64 px; re-check in the
// in-vehicle test, U11). usePendingAction gives the same behavior to custom controls (the "Use this" choices).
import { useEffect, useState } from "react";
import { useHerald } from "@/lib/store";
import { cn } from "@/lib/utils";
import { Button } from "./kit";

export interface PendingAction { busy: boolean; slow: boolean; error: string | null; disabled: boolean; replay: boolean }

export function usePendingAction(key: string): PendingAction {
  const p = useHerald((s) => s.pending[key]);
  const replay = useHerald((s) => s.source === "fixture");
  const offline = useHerald((s) => s.stale || s.conn !== "open");
  const busy = p === "pending" || p === "sent";
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!busy) { setSlow(false); return; }
    const t = window.setTimeout(() => setSlow(true), 2000);
    return () => window.clearTimeout(t);
  }, [busy]);
  return { busy, slow: busy && slow, error: typeof p === "object" ? p.error : null, disabled: busy || replay || offline, replay };
}

export function ActionNote({ a, className }: { a: PendingAction; className?: string }) {
  if (a.error) return <span role="alert" className={cn("text-meta text-high-fg", className)}>{a.error}</span>;
  if (a.slow) return <span className={cn("text-meta text-text-muted", className)}>Still waiting for the server…</span>;
  return null;
}

export function ActionButton({ pendingKey, onClick, children, busyText, variant = "secondary", size = "lg", className, disabled = false }: {
  pendingKey: string; onClick: () => void; children: React.ReactNode; busyText: string;
  variant?: "primary" | "secondary" | "ghost"; size?: "sm" | "md" | "lg"; className?: string; disabled?: boolean;
}) {
  const a = usePendingAction(pendingKey);
  return (
    <span className="inline-flex flex-col items-end gap-1">
      <Button variant={variant} size={size} onClick={onClick} disabled={a.disabled || disabled} className={className}
        title={a.replay ? "Replay: actions are off" : undefined}>
        {a.busy ? busyText : children}
      </Button>
      <ActionNote a={a} />
    </span>
  );
}
