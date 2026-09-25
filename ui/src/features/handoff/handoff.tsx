// ED handoff (UX_PLAN §3.1.9): authorizing the pre-alert, what the receiving team has (sent), what waits for the link
// (queued), and what is held on the vehicle (needs a tap or a choice); the packet log. Held and queued rows are
// prominent, sent rows quiet. Used by the overview's pre-alert card (summary) and the ED handoff page (everything).
import { ChevronDown, ChevronRight, CircleCheck, Hourglass, Lock, RefreshCw, WifiOff } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import { label, useContract } from "@/lib/contract";
import { clockTime, factValue } from "@/lib/format";
import { activeSync, erRows, reconciled, type ErRow } from "@/lib/selectors";
import type { Snapshot } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ActionButton } from "@/components/ActionButton";
import { Badge } from "@/components/kit";

export function AuthorizeForm({ s }: { s: Snapshot }) {
  const [dest, setDest] = useState("");
  const value = s.facts["transport.destination"];
  const known = value?.status === "confirmed" ? value : undefined;
  const target = known ? String(known.value) : dest.trim();
  return (
    <div className="flex flex-col gap-3">
      {!known && (
        <label className="flex flex-col gap-1.5 text-meta font-medium text-text-secondary">Destination
          <input value={dest} onChange={(e) => setDest(e.target.value)} placeholder="e.g. Regional"
            className="h-11 rounded-[var(--radius-control)] border border-border-control bg-surface-2 px-3 text-body text-text-primary placeholder:text-text-disabled" />
        </label>
      )}
      <ActionButton pendingKey="authorize" onClick={() => target && api.authorize(target)} busyText="Authorizing…" variant="primary" className="w-full">
        Authorize pre-alert{target ? ` to ${target}` : "…"}
      </ActionButton>
      <p className="text-meta text-text-muted">Then confirmed updates send automatically; unconfirmed facts never leave the vehicle.</p>
    </div>
  );
}

export function useHandoff(s: Snapshot | null) {
  const c = useContract();
  const rows = s && s.relay.authorized ? erRows(s, c) : [];
  return {
    rows,
    sent: rows.filter((r) => r.state === "sent").length,
    queued: rows.filter((r) => r.state === "queued").length,
    held: rows.filter((r) => r.state === "held").length,
  };
}

/** The tint behind a figure tile, from its number's text tone (the presentation screen's tri-tile treatment). */
const FIGURE_TINT: Record<string, string> = {
  "text-ok-fg": "bg-ok-tint", "text-low-fg": "bg-low-tint", "text-medium-fg": "bg-medium-tint",
};

/** A figure as a tinted tile: a big rounded number over a gray label, on the tone's tint (sent / queued / held). */
export function Figure({ n, label: l, tone, big = false, className }: { n: number | string; label: string; tone: string; big?: boolean; className?: string }) {
  return (
    <div className={cn("flex min-w-0 flex-col items-center rounded-[16px] p-2.5 text-center", FIGURE_TINT[tone] ?? "bg-surface-2", className)}>
      <span className={cn("rounded-num", big ? "text-kpi" : "text-value leading-7", tone)}>{n}</span>
      <span className="truncate text-meta text-text-muted">{l}</span>
    </div>
  );
}

export function LinkDownNote() {
  return (
    <p className="flex items-start gap-2 rounded-[14px] bg-low-tint px-3.5 py-2.5 text-body text-low-fg">
      <WifiOff size={18} aria-hidden className="mt-0.5 shrink-0" />The receiving link is offline. Confirmed updates wait on this vehicle and send when the link returns.
    </p>
  );
}

export function ReconciledLine({ s }: { s: Snapshot }) {
  if (!reconciled(s)) return null;
  return <p className="flex items-center gap-1.5 text-meta font-semibold text-ok-fg"><CircleCheck size={16} aria-hidden />Confirmed updates delivered · clinician receipt unknown</p>;
}

export function SyncTable({ s, rows }: { s: Snapshot; rows: ErRow[] }) {
  const c = useContract();
  return (
    <ul className="flex flex-col">
      {rows.map((row) => {
        const f = s.facts[row.key];
        return (
          <li key={row.key} className={cn("grid min-h-12 grid-cols-[1.25rem_minmax(0,11rem)_minmax(0,1fr)_auto] items-center gap-3 border-b border-border-subtle px-5 py-2 last:border-0",
            row.state === "sent" ? "text-body text-text-secondary" : "text-body font-semibold text-text-primary")}>
            {row.state === "sent" ? <CircleCheck size={17} className="text-ok-fg" aria-label="sent" />
              : row.state === "queued" ? <Hourglass size={17} className="text-low-fg" aria-label="queued" /> : <Lock size={17} className="text-medium-fg" aria-label="held" />}
            <span className="truncate">{label(c, row.key)}</span>
            <span className="truncate" title={row.why}>{row.state === "held" ? (activeSync(s)[row.key] === "sent" ? "receiving system has an earlier value" : "stays on the vehicle") : f ? factValue(f) : ""}</span>
            <span className="text-meta font-normal whitespace-nowrap text-text-muted">
              {row.state === "sent" ? "delivered"
                : row.state === "queued" ? <Badge tone="low">queued</Badge>
                : row.held === "disagree" ? <Badge tone="medium">sources disagree</Badge> : <Badge tone="medium">needs your tap</Badge>}
            </span>
          </li>
        );
      })}
      {rows.length === 0 && <li className="px-5 py-4 text-body text-text-muted">Nothing to send yet.</li>}
    </ul>
  );
}

export function PacketLog({ s }: { s: Snapshot }) {
  const c = useContract();
  const [open, setOpen] = useState<number | null>(null);
  const log = [...s.relay.log].reverse();
  return (
    <ul className="flex flex-col">
      {log.map((l) => (
        <li key={l.seq} className="border-b border-border-subtle last:border-0">
          <button type="button" onClick={() => setOpen(open === l.seq ? null : l.seq)} aria-expanded={open === l.seq}
            className="flex min-h-12 w-full items-center gap-3 px-5 text-left text-body hover:bg-surface-2/60">
            {open === l.seq ? <ChevronDown size={15} aria-hidden className="text-text-muted" /> : <ChevronRight size={15} aria-hidden className="text-text-muted" />}
            {l.result === "acked" ? <CircleCheck size={16} className="text-ok-fg" aria-hidden /> : <RefreshCw size={16} className="text-low-fg" aria-hidden />}
            <span className="num font-semibold">#{l.seq}</span>
            <span className="text-meta">{s.patients?.find((p) => p.id === l.patient)?.label ?? l.patient ?? "Current patient"}</span>
            <Badge tone={l.tier === "critical" ? "accent" : "neutral"}>{l.tier}</Badge>
            <span className="num min-w-0 truncate text-meta text-text-muted">
              {l.result === "acked" ? `${l.keys.length} field${l.keys.length === 1 ? "" : "s"} · ${l.bytes} B · ${l.rtt_ms} ms` : "failed · retrying"}
            </span>
            <span className="num ml-auto text-meta text-text-muted">{clockTime(new Date(l.ts).getTime())}</span>
          </button>
          {open === l.seq && <p className="px-5 pb-3 pl-14 text-meta text-text-secondary">{l.why.join("; ")}<br /><span className="text-text-muted">{l.keys.map((k) => label(c, k)).join(", ")}</span></p>}
        </li>
      ))}
      {log.length === 0 && <li className="px-5 py-4 text-body text-text-muted">No packets yet.</li>}
    </ul>
  );
}
