// The NOW screen (UX_PLAN §3.1) as a dashboard: the sidebar (pages, what runs on this vehicle, settings) on the app
// frame, and the page on an inset canvas with the top bar (patient, attention count, pre-alert, time) above it and the
// last capture below it. The overview is the at-a-glance page; the others hold the detail.
import { useEffect } from "react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ConnectBand, EndIncidentDialog, NewIncidentDialog, PresenterBar, StaleOverlay, Toast } from "@/components/GlobalStates";
import { useHotkeys } from "@/hooks/useHotkeys";
import { useWakeLock } from "@/hooks/useWakeLock";
import { Sidebar } from "@/layout/Sidebar";
import { TopBar } from "@/layout/TopBar";
import { TranscriptBar } from "@/layout/TranscriptBar";
import { useHerald, type Page } from "@/lib/store";
import type { FixturePlayer } from "@/lib/ws";
import { HandoffPage } from "@/pages/HandoffPage";
import { OverviewPage } from "@/pages/OverviewPage";
import { PatientPage } from "@/pages/PatientPage";
import { TranscriptPage } from "@/pages/TranscriptPage";
import { TrendsPage } from "@/pages/TrendsPage";

const PAGE: Record<Page, () => React.ReactElement | null> = {
  overview: OverviewPage, patient: PatientPage, trends: TrendsPage, handoff: HandoffPage, transcript: TranscriptPage,
};

function useDocumentSettings() {
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

export function NowApp({ player }: { player: FixturePlayer | null }) {
  useDocumentSettings();
  useHotkeys();
  const page = useHerald((s) => s.ui.page);
  const active = useHerald((s) => s.snapshot !== null && s.snapshot.incident.ended_at === null && s.source === "live");
  useWakeLock(active);
  const Current = PAGE[page];
  return (
    <TooltipProvider delayDuration={300}>
      <a href="#needs-attention" className="sr-only focus:not-sr-only focus:absolute focus:z-[70] focus:rounded-lg focus:bg-surface-3 focus:p-3">Skip to Needs attention</a>
      <div className="flex h-dvh bg-bg max-lg:h-auto max-lg:min-h-dvh max-lg:flex-col">
        <Sidebar player={player} />
        <div className="relative my-2 mr-2 flex min-w-0 flex-1 flex-col overflow-hidden rounded-[18px] border border-border-subtle bg-canvas shadow-[var(--shadow-2)] max-lg:m-0 max-lg:overflow-visible max-lg:rounded-none max-lg:border-x-0">
          <TopBar />
          <ConnectBand />
          <main key={page} className="min-h-0 flex-1 overflow-y-auto max-lg:overflow-visible">
            <Current />
          </main>
          <TranscriptBar />
          <StaleOverlay />
        </div>
      </div>
      <PresenterBar />
      <EndIncidentDialog />
      <NewIncidentDialog />
      <Toast />
    </TooltipProvider>
  );
}
