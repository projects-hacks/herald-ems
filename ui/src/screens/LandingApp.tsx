// The public landing page (the homepage, "/"): what Herald is, why it matters, how a call flows from the ambulance to
// the ED, what it does today, the evidence, and the edge box it runs on, in one scroll.

import { Features, Handover } from "@/features/landing/Features";
import { Hero, Nav } from "@/features/landing/Hero";
import { Closing, Edge, Footer } from "@/features/landing/Outro";
import { Results } from "@/features/landing/Results";
import { Journey, Problem, Stats } from "@/features/landing/Story";
import { Trust } from "@/features/landing/Trust";

export function LandingApp() {
  return (
    <div className="lp-root">
      <Nav />
      <main>
        <Hero />
        <Stats />
        <Problem />
        <Journey />
        <Features />
        <Handover />
        <Results />
        <Trust />
        <Edge />
        <Closing />
      </main>
      <Footer />
    </div>
  );
}
