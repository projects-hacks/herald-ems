// The public landing page: what Herald is, why it matters, how it works, and the evidence, in one scroll.

import { Hero, Nav } from "@/features/landing/Hero";
import { Closing, Edge, Footer } from "@/features/landing/Outro";
import { Results } from "@/features/landing/Results";
import { Features, HowItWorks, Problem, Stats } from "@/features/landing/Story";
import { Trust } from "@/features/landing/Trust";

export function LandingApp() {
  return (
    <div className="lp-root">
      <Nav />
      <main>
        <Hero />
        <Stats />
        <Problem />
        <HowItWorks />
        <Features />
        <Trust />
        <Results />
        <Edge />
        <Closing />
      </main>
      <Footer />
    </div>
  );
}
