// Keep the screen awake while an incident is active (UX_PLAN §3.1.13). Browsers may refuse; that is fine.
import { useEffect } from "react";

export function useWakeLock(active: boolean) {
  useEffect(() => {
    if (!active || !("wakeLock" in navigator)) return;
    let lock: WakeLockSentinel | null = null;
    let cancelled = false;
    const request = () => navigator.wakeLock.request("screen").then((l) => {
      if (cancelled) void l.release(); else lock = l;
    }).catch(() => {});
    void request();
    const onVisible = () => document.visibilityState === "visible" && request();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisible);
      void lock?.release();
    };
  }, [active]);
}
