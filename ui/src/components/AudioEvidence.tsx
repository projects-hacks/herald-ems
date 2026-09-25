import { useState } from "react";
export function AudioEvidence({ id }: { id: string | null | undefined }) {
  const [error, setError] = useState(false);
  if (!id) return null;
  return <span className="mt-2 block max-w-full"><audio aria-label="Play source audio" controls preload="none" src={`/api/audio/${encodeURIComponent(id)}`} onError={() => setError(true)} className="h-12 max-w-full" />
    {error && <span role="status" className="text-meta text-medium-fg">Audio evidence is unavailable on this device.</span>}</span>;
}
