import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// tailwind-merge must know Herald's type scale (src/index.css @theme): otherwise it reads "text-kpi" as a color and
// drops it when a real color follows, e.g. cn("text-kpi", "text-ok-fg") would lose the size.
const twMerge = extendTailwindMerge({
  extend: { theme: { text: ["meta", "label", "body", "title", "critical", "value", "button", "clock", "kpi", "hero"] } },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
