import { useEffect, useRef, useState } from "react";
import { useHerald } from "@/lib/store";
import { AmbientCapture, initialAmbient } from "./ambient";

export function useAmbient() {
  const incident = useHerald((s) => s.snapshot?.incident.id);
  // Capture belongs to one reviewed, open patient in one tab. Feed blips do not tear down uploads, which retry independently.
  const blocked = useHerald((s) => s.source !== "live" || s.captureElsewhere || !!s.snapshot?.incident.ended_at || !!s.snapshot?.incident.handed_over_at || !!s.snapshot?.restored);
  const paused = useHerald((s) => s.ui.capturePaused);
  const [status, setStatus] = useState(initialAmbient);
  const capture = useRef<AmbientCapture | null>(null);
  useEffect(() => {
    setStatus({ ...initialAmbient, message: blocked
      ? "Capture unavailable · unsent audio is not retained. Review notes for gaps."
      : "Microphone off · start listening for this patient" });
    if (!incident || blocked) return;
    const session = new AmbientCapture(incident, setStatus); capture.current = session;
    if (!useHerald.getState().ui.capturePaused) void session.start();   // continuous: listening starts with the call
    // Listening continues while the tab is in the background (the browser shows its own recording indicator); only
    // the medic's pause, a new call or leaving the page ends it.
    return () => { session.dispose(); capture.current = null; };
  }, [incident, blocked]);
  useEffect(() => { const s = capture.current; if (!s) return; if (paused) s.pause(); else void s.start(); }, [paused]);
  return { status, blocked: blocked || !incident, start: () => capture.current?.start(), pause: () => capture.current?.pause() };
}
