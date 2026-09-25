import { useEffect, useRef, useState } from "react";
import { useHerald } from "@/lib/store";
import { AmbientCapture, initialAmbient } from "./ambient";

export function useAmbient() {
  const incident = useHerald((s) => s.snapshot?.incident.id);
  const blocked = useHerald((s) => s.source !== "live" || s.stale || s.conn !== "open");
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
    // a hidden tab pauses the microphone; coming back resumes it unless the medic paused it
    const hidden = () => { if (document.hidden) session.pause(); else if (!useHerald.getState().ui.capturePaused) void session.start(); };
    document.addEventListener("visibilitychange", hidden);
    return () => { document.removeEventListener("visibilitychange", hidden); session.dispose(); capture.current = null; };
  }, [incident, blocked]);
  useEffect(() => { const s = capture.current; if (!s) return; if (paused) s.pause(); else void s.start(); }, [paused]);
  return { status, blocked: blocked || !incident, start: () => capture.current?.start(), pause: () => capture.current?.pause() };
}
