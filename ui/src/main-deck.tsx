import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "@fontsource-variable/nunito";
import "./index.css";
import { DeckApp } from "@/screens/DeckApp";

// Standalone pitch deck page (deck.html) — no backend, no live connection. Keyboard: ← / → / space.
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <DeckApp />
  </StrictMode>,
);
