import { useHerald } from "@/lib/store";
export function CompactStatus({ always = false }: { always?: boolean }) {
  const s = useHerald((state) => state.snapshot), health = useHerald((state) => state.health);
  const replay = useHerald((state) => state.source === "fixture");
  const disconnected = useHerald((state) => state.conn !== "open" || state.stale);
  return <div className={`flex flex-wrap gap-3 border-b border-border-subtle px-5 py-2 text-meta ${always ? "" : "lg:hidden"}`} role="status" aria-label="Vehicle and ED status">
    {replay ? <span>REPLAY · actions off</span> : <>
      <span>{disconnected ? s ? "VEHICLE OFFLINE · showing last state" : "Waiting for vehicle connection" : s ? "Vehicle connected" : "Connected · waiting for patient data"}</span>
      <span className={health?.llm_available === false ? "text-medium-fg" : ""}>{health?.llm_available === false ? "Extraction model not running · words kept, no new facts" : health?.llm_available ? "Extraction model ready" : "Model status unknown"}</span>
    </>}
    <span>{!s ? "ED status unavailable" : !s.relay.configured ? "ED not configured" : !s.relay.authorized ? "ED relay not authorized" : s.relay.link === "down" ? "ED OFFLINE · updates held on vehicle" : `ED link: ${s.relay.link}`}</span>
  </div>;
}
