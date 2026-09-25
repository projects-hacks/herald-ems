import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "./index.css";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { loadContract } from "@/lib/contract";
import { connectLive, playFixture, type FixturePlayer } from "@/lib/ws";
import { NowApp } from "@/screens/NowApp";

const q = new URLSearchParams(location.search);
const fixture = q.get("fixture");
void loadContract();
let player: FixturePlayer | null = null;
if (fixture) player = playFixture(fixture, Number(q.get("speed")) || 1, q.has("at") ? Number(q.get("at")) : null);
else connectLive();
createRoot(document.getElementById("root")!).render(<StrictMode><ErrorBoundary><NowApp player={player} /></ErrorBoundary></StrictMode>);
