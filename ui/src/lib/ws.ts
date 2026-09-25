// Connection to the Herald server's /ws, and the fixture player (UX_PLAN §5.7, §5.8).
// - live: one socket; the client sends "ping" every 1 s and the server answers "pong", so silence can be told apart
//   from a dead server. Stale = open but nothing for > 3 s, or closed after data arrived. Timestamps (not timer
//   counts) decide staleness, so background-tab throttling can't raise false alarms. Reconnect: 0.5, 1, 2, then 2 s.
// - fixture (?fixture=<name>&speed=<n>): replays ui/public/fixtures/<name>.jsonl with its recorded timing.
import { useHerald } from "./store";
import type { FixtureLine, NowMessage } from "./types";

export const HEARTBEAT_MS = 1000;
export const STALE_MS = 3000;
export const CANT_CONNECT_MS = 5000;
const BACKOFF_MS = [500, 1000, 2000];

export function isStale(now: number, conn: string, lastMessageAt: number, hasData: boolean): boolean {
  if (conn === "open") return lastMessageAt > 0 && now - lastMessageAt > STALE_MS;
  return conn === "closed" && hasData;
}

function handle(msg: NowMessage) {
  const st = useHerald.getState();
  useHerald.setState({ lastMessageAt: performance.now() });
  if (msg.type === "state") st.setSnapshot(msg.state);
}

export function connectLive(url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`) {
  let ws: WebSocket | null = null;
  let attempt = 0;
  let ping: number | undefined;
  let stopped = false;
  let reconnect: number | undefined;
  useHerald.setState({ conn: "connecting", connectingSince: performance.now(), source: "live" });

  const open = () => {
    if (stopped) return;
    ws = new WebSocket(url);
    ws.onopen = () => {
      attempt = 0;
      useHerald.setState({ conn: "open", lastMessageAt: performance.now() });
      ping = window.setInterval(() => ws?.readyState === WebSocket.OPEN && ws.send("ping"), HEARTBEAT_MS);
    };
    ws.onmessage = (e) => {
      try {
        handle(JSON.parse(e.data as string) as NowMessage);
      } catch {
        /* a malformed message is ignored; the heartbeat still decides staleness */
      }
    };
    ws.onclose = () => {
      window.clearInterval(ping);
      if (stopped) return;
      const was = useHerald.getState().conn;
      useHerald.setState({ conn: "closed", ...(was === "open" ? { connectingSince: performance.now() } : {}) });
      reconnect = window.setTimeout(open, BACKOFF_MS[Math.min(attempt++, BACKOFF_MS.length - 1)]);
    };
  };
  open();

  const check = window.setInterval(() => {
    const s = useHerald.getState();
    const stale = isStale(performance.now(), s.conn, s.lastMessageAt, s.snapshot !== null);
    if (stale !== s.stale) useHerald.setState({ stale });
  }, 500);

  const health = window.setInterval(pollHealth, 5000);
  pollHealth();

  return () => {
    stopped = true;
    window.clearInterval(check);
    window.clearInterval(health);
    window.clearInterval(ping);
    window.clearTimeout(reconnect);
    ws?.close();
  };
}

async function pollHealth() {
  try {
    const r = await fetch("/api/health", { signal: AbortSignal.timeout(3000) });
    if (r.ok) useHerald.setState({ health: await r.json() });
  } catch {
    /* the socket state already tells the medic the server is unreachable */
  }
}

// ---------- fixture player ----------
export function parseFixture(text: string): FixtureLine[] {
  return text.split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l) as FixtureLine)
    .filter((l) => l.msg.type === "state");
}

/** Milliseconds to wait before dispatching line i (the recorded gap, divided by the speed). */
export function fixtureDelay(lines: FixtureLine[], i: number, speed: number): number {
  if (i === 0) return 0;
  return Math.max(0, (lines[i].t_ms - lines[i - 1].t_ms) / Math.max(speed, 0.1));
}

export interface FixturePlayer { play(): void; pause(): void; step(): void; restart(): void; setSpeed(s: number): void }

export function playFixture(name: string, speed = 1, at: number | null = null, fetchText = (u: string) => fetch(u).then((r) => {
  if (!r.ok) throw new Error(`fixture '${name}' not found (${r.status})`);
  return r.text();
})): FixturePlayer {
  let lines: FixtureLine[] = [];
  let timer: number | undefined;
  const set = (patch: Partial<NonNullable<ReturnType<typeof useHerald.getState>["fixture"]>>) => {
    const f = useHerald.getState().fixture!;
    useHerald.setState({ fixture: { ...f, ...patch } });
  };
  useHerald.setState({ source: "fixture", conn: "open", fixture: { name, index: 0, total: 0, playing: true, speed } });

  const dispatchAt = (i: number) => {
    handle(lines[i].msg);
    set({ index: i + 1 });
  };
  const schedule = () => {
    const f = useHerald.getState().fixture!;
    if (!f.playing || f.index >= lines.length) {
      if (f.index >= lines.length) set({ playing: false });
      return;
    }
    timer = window.setTimeout(() => {
      dispatchAt(useHerald.getState().fixture!.index);
      schedule();
    }, fixtureDelay(lines, f.index, f.speed));
  };

  fetchText(`/fixtures/${encodeURIComponent(name)}.jsonl`).then((t) => {
    lines = parseFixture(t);
    set({ total: lines.length });
    if (at !== null) {                         // ?at=N: jump to message N and pause (rehearsal, screenshots)
      const n = Math.max(1, Math.min(at, lines.length));
      for (let i = 0; i < n; i++) handle(lines[i].msg);
      set({ index: n, playing: false });
      return;
    }
    schedule();
  }).catch((e: Error) => useHerald.getState().showToast(e.message));

  return {
    play: () => { set({ playing: true }); window.clearTimeout(timer); schedule(); },
    pause: () => { window.clearTimeout(timer); set({ playing: false }); },
    step: () => {
      window.clearTimeout(timer);
      const i = useHerald.getState().fixture!.index;
      set({ playing: false });
      if (i < lines.length) dispatchAt(i);
    },
    restart: () => { window.clearTimeout(timer); set({ index: 0, playing: true }); schedule(); },
    setSpeed: (s) => { set({ speed: s }); },
  };
}
