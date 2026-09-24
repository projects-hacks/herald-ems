// The attention queue for the current snapshot, shared by the queue card, the sidebar badge and the top bar.
import { useMemo } from "react";
import { attention, type Attention } from "@/lib/selectors";
import { useHerald } from "@/lib/store";

export function useAttention(): Attention | null {
  const s = useHerald((st) => st.snapshot);
  const seen = useHerald((st) => st.ui.seenAlerts);
  const arrival = useHerald((st) => st.alertArrival);
  const holdMark = useHerald((st) => st.holdMark);
  return useMemo(() => (s ? attention(s, seen, arrival, holdMark) : null), [s, seen, arrival, holdMark]);
}
