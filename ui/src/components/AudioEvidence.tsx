import { useState } from "react";
import { useHerald } from "@/lib/store";

/** The clip a fact was heard in. Audio is deleted when the encounter ends (hand over or finish), so an ended call
 * says that instead of drawing a player that cannot play; a clip that fails to load hides its player. */
export function AudioEvidence({ id }: { id: string | null | undefined }) {
  const [error, setError] = useState(false);
  const disposed = useHerald((s) => !!s.snapshot?.incident.media_disposal);
  if (!id) return null;
  if (disposed) return <span className="mt-1 block text-meta text-text-muted">Audio deleted when the encounter ended</span>;
  if (error) return <span role="status" className="mt-1 block text-meta text-text-muted">Audio clip not available</span>;
  return <span className="mt-2 block max-w-full"><audio aria-label="Play source audio" controls preload="none" src={`/api/audio/${encodeURIComponent(id)}`} onError={() => setError(true)} className="h-12 max-w-full" /></span>;
}
