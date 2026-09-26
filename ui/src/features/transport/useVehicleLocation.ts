// The vehicle's position for road drive times: this tablet's location, sent to the vehicle server (never further;
// herald/api/routes/transport.py keeps it in memory for routing only). Only the tab that owns capture sends it, only
// on a live open call, and only while Settings allows it. A new fix is sent when the vehicle has moved or every 15 s.
import { useEffect, useState } from "react";
import { authHeaders } from "@/lib/authToken";
import { useHerald } from "@/lib/store";

export type LocationState = "off" | "waiting" | "sharing" | "denied" | "unavailable";
const EVERY_MS = 15000, MOVED_M = 30;

function metres(a: GeolocationCoordinates, b: GeolocationCoordinates): number {
  const r = Math.PI / 180, dLat = (b.latitude - a.latitude) * r, dLon = (b.longitude - a.longitude) * r;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.latitude * r) * Math.cos(b.latitude * r) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.sqrt(h));
}

export function useVehicleLocation(): LocationState {
  const enabled = useHerald((s) => s.ui.shareLocation && s.source === "live" && !s.captureElsewhere
    && !!s.snapshot && !s.snapshot.incident.ended_at && !!s.snapshot.transport);
  const [state, setState] = useState<LocationState>("off");
  useEffect(() => {
    const geo = typeof navigator !== "undefined" ? navigator.geolocation : undefined;
    if (!enabled) { setState("off"); return; }
    if (!geo) { setState("unavailable"); return; }
    setState("waiting");
    let last: { at: number; coords: GeolocationCoordinates } | null = null;
    const watch = geo.watchPosition((pos) => {
      setState("sharing");
      if (last && Date.now() - last.at < EVERY_MS && metres(last.coords, pos.coords) < MOVED_M) return;
      last = { at: Date.now(), coords: pos.coords };
      void fetch("/api/transport/position", {
        method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ lat: pos.coords.latitude, lon: pos.coords.longitude, accuracy_m: pos.coords.accuracy,
                               at: new Date(pos.timestamp).toISOString() }),
        signal: AbortSignal.timeout(5000),
      }).catch(() => { last = null; });      // retried with the next fix
    }, (err) => setState(err.code === err.PERMISSION_DENIED ? "denied" : "unavailable"),
    { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 });
    return () => geo.clearWatch(watch);
  }, [enabled]);
  return state;
}
