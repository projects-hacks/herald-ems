// The one "N h M m ago" formatter for clock values (LKW on the medic tiles and the presentation screen). Feed it
// snapshot-anchored seconds (format.clockSeconds), never the viewer's wall clock: in a replay the two can disagree.
export function elapsedAgo(totalSeconds: number): string {
  const minutes = Math.max(0, Math.floor(totalSeconds / 60));
  return minutes >= 60 ? `${Math.floor(minutes / 60)} h ${minutes % 60} m ago` : `${minutes} m ago`;
}
