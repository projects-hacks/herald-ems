import { useEffect, useRef, useState } from "react";
import { useHerald } from "@/lib/store";
import { AmbientCapture, initialAmbient } from "./ambient";

export function useAmbient() {
  const incident = useHerald((s) => s.snapshot?.incident.id);
  // Only a replay blocks capture. A stale or dropped connection to the screen's feed does not: uploads are separate
  // requests that wait and retry, so a link blip no longer tears the microphone down and rebuilds it.
  const blocked = useHerald((s) => s.source !== "live");
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
