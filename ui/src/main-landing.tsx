import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/inter";
import "./index.css";
import "@/features/landing/landing.css";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { LandingApp } from "@/screens/LandingApp";

// Public landing page (landing/index.html, served at /landing/): static, no backend, no live connection.
// ?still turns motion off (the app's data-reduced-motion switch), so screenshots show the settled page.
if (new URLSearchParams(location.search).has("still")) document.documentElement.dataset.reducedMotion = "true";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <LandingApp />
    </ErrorBoundary>
  </StrictMode>,
);
