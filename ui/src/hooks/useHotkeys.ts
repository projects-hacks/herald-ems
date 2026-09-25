// Global keys (docs/API_CONTRACT.md). Ignored while typing in a field or while a dialog is open. Push-to-talk keys
// (Space, F) belong to the capture bar (U4) and are not handled here.
import { useEffect } from "react";
import { api } from "@/lib/api";
import { useHerald, type TypeScale } from "@/lib/store";

const NEXT_SCALE: Record<number, TypeScale> = { 1: 1.25, 1.25: 1.5, 1.5: 1 };
async function changeLink(mode: "good" | "weak" | "down") {
  if (!await api.netem(mode)) useHerald.getState().showToast("Link change failed. The previous setting may still apply; check ED status.");
}

function typing(t: EventTarget | null): boolean {
  const el = t as HTMLElement | null;
  return !!el && (["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) || el.isContentEditable);
}

export function useHotkeys() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (typing(e.target) || document.querySelector("[role=dialog][data-state=open]")) return;
      const { ui, setUi } = useHerald.getState();
      if (!e.shiftKey || e.ctrlKey || e.metaKey || e.altKey) return;
      const k = e.key.toUpperCase();
      if (k === "E") setUi({ page: "transcript" });
      else if (k === "T") setUi({ typeScale: NEXT_SCALE[ui.typeScale] });
      else if (k === "L") setUi({ theme: ui.theme === "dark" ? "light" : "dark" });
      else if (ui.page === "settings" && k === "G") void changeLink("good");
      else if (ui.page === "settings" && k === "W") void changeLink("weak");
      else if (ui.page === "settings" && k === "D") void changeLink("down");
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
