import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/atkinson-hyperlegible-next";
import "@fontsource-variable/atkinson-hyperlegible-mono";
import "@fontsource/saira-condensed/600.css";
import "@fontsource/saira-condensed/700.css";
import "./index.css";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { loadContract } from "@/lib/contract";
import { connectLive, playFixture, type FixturePlayer } from "@/lib/ws";
import { NowApp } from "@/screens/NowApp";

// ?fixture=<name>&speed=<n> replays a recorded session with no backend; otherwise connect live.
const q = new URLSearchParams(location.search);
const fixture = q.get("fixture");
let player: FixturePlayer | null = null;
void loadContract();
if (fixture) player = playFixture(fixture, Number(q.get("speed")) || 1, q.has("at") ? Number(q.get("at")) : null);
else connectLive();

createRoot(document.getElementById("root")!).render(<StrictMode><ErrorBoundary><NowApp player={player} /></ErrorBoundary></StrictMode>);
