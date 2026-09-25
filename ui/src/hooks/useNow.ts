// One shared 1 Hz tick for every clock on the screen (UX_PLAN §3.1.3), so all clocks change together.
import { useSyncExternalStore } from "react";

let now = Date.now();
const subs = new Set<() => void>();
let timer: number | undefined;

function subscribe(cb: () => void) {
  subs.add(cb);
  if (timer === undefined) {
    timer = window.setInterval(() => { now = Date.now(); subs.forEach((s) => s()); }, 1000);
  }
  return () => {
    subs.delete(cb);
    if (!subs.size) { window.clearInterval(timer); timer = undefined; }
  };
}
export function useNow(): number {
  return useSyncExternalStore(subscribe, () => now, () => now);
}
