import { EndIncidentDialog, NewIncidentDialog, Toast } from "@/components/GlobalStates";
import { useHotkeys } from "@/hooks/useHotkeys";
import { useDocumentSettings } from "@/hooks/useDocumentSettings";
import { useWakeLock } from "@/hooks/useWakeLock";
import { useHerald } from "@/lib/store";
import type { FixturePlayer } from "@/lib/ws";
import { CabinApp } from "@/features/cabin/CabinApp";

/** The single medic application; evidence details live within its care pages. */
export function NowApp({ player }: { player: FixturePlayer | null }) {
  useDocumentSettings();
  useHotkeys();
  const active = useHerald((s) => s.snapshot !== null && s.snapshot.incident.ended_at === null && s.source === "live");
  useWakeLock(active);
  return <>
    <a href="#cabin-attention" className="sr-only focus:not-sr-only focus:absolute focus:z-[70] focus:rounded-lg focus:bg-surface-3 focus:p-3">Skip to Needs attention</a>
    <CabinApp player={player} />
    <EndIncidentDialog /><NewIncidentDialog /><Toast />
  </>;
}
