import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "@fontsource-variable/nunito";
import "./index.css";
import { loadContract } from "@/lib/contract";
import { connectLive, playFixture, type FixturePlayer } from "@/lib/ws";
import { NowApp } from "@/screens/NowApp";

// ?fixture=<name>&speed=<n> replays a recorded session with no backend (UX_PLAN §5.8); otherwise connect live.
const q = new URLSearchParams(location.search);
const fixture = q.get("fixture");
let player: FixturePlayer | null = null;
void loadContract();
if (fixture) player = playFixture(fixture, Number(q.get("speed")) || 1, q.has("at") ? Number(q.get("at")) : null);
else connectLive();

createRoot(document.getElementById("root")!).render(<StrictMode><NowApp player={player} /></StrictMode>);
