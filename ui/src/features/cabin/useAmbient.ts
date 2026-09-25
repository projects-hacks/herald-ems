import { useEffect, useRef, useState } from "react";
import { useHerald } from "@/lib/store";
import { AmbientCapture, initialAmbient } from "./ambient";

export function useAmbient() {
  const incident = useHerald((s) => s.snapshot?.incident.id);
  const blocked = useHerald((s) => s.source !== "live" || s.stale || s.conn !== "open");
  const [status, setStatus] = useState(initialAmbient);
  const capture = useRef<AmbientCapture | null>(null);
  useEffect(() => {
    setStatus({ ...initialAmbient, message: blocked
      ? "Capture unavailable · unsent audio is not retained. Review notes for gaps."
      : "Microphone off · start listening for this patient" });
    if (!incident || blocked) return;
    const session = new AmbientCapture(incident, setStatus); capture.current = session;
    const hidden = () => { if (document.hidden) session.pause(); };
    document.addEventListener("visibilitychange", hidden);
    return () => { document.removeEventListener("visibilitychange", hidden); session.dispose(); capture.current = null; };
  }, [incident, blocked]);
  return { status, blocked: blocked || !incident, start: () => capture.current?.start(), pause: () => capture.current?.pause() };
}
