// The vehicle's position for road drive times: this tablet's location, sent to the vehicle server (never further;
// herald/api/routes/transport.py keeps it in memory for routing only). Only the tab that owns capture sends it, only
// on a live open call, and only while Settings allows it. A new fix is sent when the vehicle has moved or every 15 s.
//
// watchPosition alone is not enough: a device that is not moving gets no new callback (live report 2026-09-26: one
// fix at the start of the call, the destination set minutes later, and the ETA stayed the crew's estimate because
// the server treats a position older than 2 minutes as unknown). So the position is also re-read on a timer, and
// each fix carries its age measured on this device (`age_s`), which a tablet clock that differs from the vehicle
// server's cannot distort.
import { useEffect, useState } from "react";
import { authHeaders } from "@/lib/authToken";
import { useHerald } from "@/lib/store";

export type LocationState = "off" | "waiting" | "sharing" | "denied" | "unavailable";
export const EVERY_MS = 15000;
const MOVED_M = 30;

function metres(a: GeolocationCoordinates, b: GeolocationCoordinates): number {
  const r = Math.PI / 180, dLat = (b.latitude - a.latitude) * r, dLon = (b.longitude - a.longitude) * r;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.latitude * r) * Math.cos(b.latitude * r) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.sqrt(h));
}

/** The body posted for one fix: where, how precise, and how old it is by this device's own clock. */
export function positionBody(pos: GeolocationPosition, nowMs: number = Date.now()) {
  return { lat: pos.coords.latitude, lon: pos.coords.longitude, accuracy_m: pos.coords.accuracy,
           at: new Date(pos.timestamp).toISOString(), age_s: Math.max(0, (nowMs - pos.timestamp) / 1000) };
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
    const send = (pos: GeolocationPosition) => {
      setState("sharing");
      // a second of slack, so the timed re-read is never skipped by a tick of jitter
      if (last && Date.now() - last.at < EVERY_MS - 1000 && metres(last.coords, pos.coords) < MOVED_M) return;
      last = { at: Date.now(), coords: pos.coords };
      void fetch("/api/transport/position", {
        method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(positionBody(pos)), signal: AbortSignal.timeout(5000),
      }).catch(() => { last = null; });      // retried with the next fix
    };
    const options = { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 };
    const watch = geo.watchPosition(send, (err) => setState(err.code === err.PERMISSION_DENIED ? "denied" : "unavailable"), options);
    const timer = window.setInterval(() => geo.getCurrentPosition(send, (err) => {
      if (err.code === err.PERMISSION_DENIED) setState("denied");   // a missed timed fix is retried on the next tick
    }, options), EVERY_MS);
    return () => { geo.clearWatch(watch); window.clearInterval(timer); };
  }, [enabled]);
  return state;
}
