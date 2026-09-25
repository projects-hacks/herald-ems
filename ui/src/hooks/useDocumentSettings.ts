import { useEffect } from "react";
import { useHerald } from "@/lib/store";

export function useDocumentSettings() {
  const theme = useHerald((s) => s.ui.theme);
  const scale = useHerald((s) => s.ui.typeScale);
  const reduced = useHerald((s) => s.ui.reducedMotion);
  useEffect(() => {
    const el = document.documentElement;
    el.dataset.theme = theme;
    el.dataset.reducedMotion = String(reduced);
    el.style.setProperty("--type-scale", String(scale));
  }, [theme, scale, reduced]);
}
