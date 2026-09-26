// One Herald tab captures at a time. Two tabs listening to the same cabin upload every sentence twice, and the
// second camera is refused by the server (one frame stream per call). The browser's Web Locks API gives the
// microphone and camera to the first tab; another tab shows the call without capturing, and takes over by itself
// when the capturing tab closes. Without the API (older browsers, tests) every tab may capture, as before.
import { useEffect } from "react";
import { useHerald } from "@/lib/store";
export { initialCaptureElsewhere } from "@/lib/store";

const LOCK = "herald-capture";

export function useCaptureOwner(): void {
  useEffect(() => {
    const locks = (navigator as Navigator & { locks?: LockManager }).locks;
    if (!locks) { useHerald.setState({ captureElsewhere: false }); return; }
    const abort = new AbortController();
    let release: () => void = () => {};
    const held = new Promise<void>((done) => { release = done; });
    locks.request(LOCK, { signal: abort.signal }, async () => {
      useHerald.setState({ captureElsewhere: false });
      await held;                                             // kept for as long as this page shows Herald
    }).catch(() => { /* aborted on unmount */ });
    return () => { abort.abort(); release(); useHerald.setState({ captureElsewhere: false }); };
  }, []);
}
