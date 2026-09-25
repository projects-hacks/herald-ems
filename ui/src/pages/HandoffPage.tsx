// ED handoff (UX_PLAN §3.1.9): the figures, every field the ED set carries with its state, and the packet log.
import { Send } from "lucide-react";
import { HandoffReport } from "@/features/handoff/HandoffReport";
import { useHerald } from "@/lib/store";
import { Card, CardHeader, Count, EmptyState, PageHeader } from "@/components/kit";
import { AuthorizeForm, Figure, LinkDownNote, PacketLog, ReconciledLine, SyncTable, useHandoff } from "@/features/handoff/handoff";

export function HandoffPage() {
  const s = useHerald((st) => st.snapshot);
  const h = useHandoff(s);
  if (!s) return null;
  const r = s.relay;
  const header = <><PageHeader title="ED handoff" description={r.authorized ? `Pre-alert to ${r.authorized.destination} · ${r.authorized.scope}` : "What the receiving team has, what's queued, and what stays on the vehicle."} /><HandoffReport /></>;
  if (!r.configured) return <div className="flex flex-col gap-5 p-6">{header}<Card><EmptyState icon={Send} tone="neutral" title="The ED link isn't set up">Set HERALD_ED_URL on this vehicle to send pre-alerts.</EmptyState></Card></div>;
  if (!r.authorized) return <div className="flex flex-col gap-5 p-6">{header}<Card className="max-w-md p-5"><AuthorizeForm s={s} /></Card></div>;
  return (
    <div className="flex flex-col gap-5 p-6">
      {header}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Figure big n={h.sent} label="fields sent" tone="text-ok-fg" />
        <Figure big n={h.queued} label="queued for the link" tone={h.queued ? "text-low-fg" : "text-text-muted"} />
        <Figure big n={h.held} label="held on the vehicle" tone={h.held ? "text-medium-fg" : "text-text-muted"} />
        <Figure big n={`${(r.bytes_sent / 1000).toFixed(1)} kB`} label={`${r.packets_acked} packets · ${r.retries} retries`} tone="text-text-primary" />
      </div>
      {r.link === "down" && <LinkDownNote />}
      <ReconciledLine s={s} />
      <div className="grid grid-cols-12 gap-4 max-lg:grid-cols-1">
        <Card className="col-span-7 max-lg:col-span-1" aria-labelledby="fields-h">
          <CardHeader title="Fields" id="fields-h" subtitle="In the order they are sent" badge={<Count n={h.rows.length} />} />
          <div className="border-t border-border-subtle"><SyncTable s={s} rows={h.rows} /></div>
        </Card>
        <Card className="col-span-5 max-lg:col-span-1" aria-labelledby="log-h">
          <CardHeader title="Packet log" id="log-h" subtitle="Newest first · tap a packet for why it was sent" badge={<Count n={r.log.length} />} />
          <div className="border-t border-border-subtle"><PacketLog s={s} /></div>
        </Card>
      </div>
    </div>
  );
}
