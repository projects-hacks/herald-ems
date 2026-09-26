// On this box: what the call's AI cost here, from GET /api/telemetry, polled while Settings is open. Cloud AI calls
// first (always 0: nothing leaves the vehicle), then the model's tokens and speed, the GPU's power and energy, energy
// per call by kind, and the cost here against the same work in the cloud with the prices it assumes and their
// sources. A recorded replay has no box to ask, so it says so instead of showing numbers.
import { useEffect, useState } from "react";
import { clockTime } from "@/lib/format";
import { useHerald } from "@/lib/store";
import { duration, energyPerCall, fetchTelemetry, fmt, usd } from "@/lib/telemetry";
import type { Telemetry } from "@/lib/types";

const POLL_MS = 5000;

function useTelemetry(enabled: boolean) {
  const [data, setData] = useState<Telemetry | null>(null);
  const [at, setAt] = useState<number | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const abort = new AbortController();
    const load = async () => {
      const t = await fetchTelemetry(abort.signal);
      if (cancelled) return;
      if (t) { setData(t); setAt(Date.now()); }
      setFailed(!t);
    };
    void load();
    const timer = window.setInterval(() => void load(), POLL_MS);
    return () => { cancelled = true; abort.abort(); window.clearInterval(timer); };
  }, [enabled]);
  return { data, at, failed };
}

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return <div className="telemetry-stat">
    <dt>{label}</dt>
    <dd className="num">{value}</dd>
    {note && <dd className="telemetry-note">{note}</dd>}
  </div>;
}

export function TelemetryPanel() {
  const replay = useHerald((st) => st.source === "fixture");
  const { data: t, at, failed } = useTelemetry(!replay);
  if (replay) return <p className="cabin-settings-note" role="status">Telemetry is available when Herald is running on the box.</p>;
  if (!t) return <p className="cabin-settings-note" role="status">{failed
    ? "The box did not answer. Telemetry is available when Herald is running on the box; retrying every 5 seconds."
    : "Loading telemetry…"}</p>;
  const ms = t.model_server, a = t.assumptions, cost = t.cost;
  const perCall = energyPerCall(t.requests?.recent);
  const since = duration(t.since_s);
  const cloud = t.cloud_ai_calls;
  const src = (key: string) => (a?.sources?.[key] ? ` (${a.sources[key]})` : "");
  return <div className="telemetry">
    <div className="telemetry-cloud" data-zero={cloud === 0 || undefined}>
      <span className="num telemetry-cloud-n">{fmt(cloud)}</span>
      <span><strong>Cloud AI calls</strong><br />{cloud === 0 ? "Every model ran on this box." : "Calls this session that left the box."}</span>
    </div>

    <h3 className="telemetry-heading">Language model</h3>
    <dl className="telemetry-grid">
      <Stat label="Tokens in" value={fmt(t.tokens?.prompt)} note="this session" />
      <Stat label="Tokens out" value={fmt(t.tokens?.completion)} note="this session" />
      <Stat label="Generation speed" value={fmt(ms?.generation_tok_s_last_30s, 1, "tokens/s")}
        note={ms?.generation_tok_s_last_30s == null ? "idle in the last 30 s" : "last 30 s"} />
      <Stat label="Mean request time" value={fmt(ms?.mean_request_latency_s, 2, "s")} note="model server" />
    </dl>

    <h3 className="telemetry-heading">GPU power and energy</h3>
    <dl className="telemetry-grid">
      <Stat label="Power now" value={fmt(t.power_w_now, 1, "W")} />
      <Stat label="60 s average" value={fmt(t.power_w_avg_60s, 1, "W")} />
      <Stat label="Energy used" value={fmt(t.energy_wh, 2, "Wh")} note={since ? `in ${since}` : undefined} />
    </dl>

    <h3 className="telemetry-heading">Energy per call</h3>
    {perCall.length ? <table className="telemetry-table">
      <caption className="sr-only">Energy per call, by kind</caption>
      <thead><tr><th scope="col">Kind</th><th scope="col">Calls</th><th scope="col">Energy per call</th><th scope="col">Average power</th></tr></thead>
      <tbody>{perCall.map((row) => <tr key={row.kind}>
        <th scope="row">{row.label}</th>
        <td className="num">{row.measured === row.calls ? row.calls : `${row.calls} (${row.measured} measured)`}</td>
        <td className="num">{fmt(row.joules, 1, "J")}</td>
        <td className="num">{fmt(row.watts, 1, "W")}</td>
      </tr>)}</tbody>
    </table> : <p className="cabin-settings-note">No model calls yet.</p>}
    {perCall.length > 0 && <p className="telemetry-note">From the last {perCall.reduce((n, r) => n + r.calls, 0)} calls. GPU power is sampled
      every few seconds, so a short call can go unmeasured: the averages are over the measured calls, and a dash means none was long enough.</p>}

    <h3 className="telemetry-heading">Cost</h3>
    <dl className="telemetry-grid">
      <Stat label="On this box" value={usd(cost?.local_usd)} note="electricity" />
      <Stat label="Same work in the cloud" value={usd(cost?.cloud_equivalent_usd)}
        note={cost?.cloud_breakdown ? `text model ${usd(cost.cloud_breakdown.llm_usd)}, speech to text ${usd(cost.cloud_breakdown.stt_usd)}` : undefined} />
      <Stat label="Saved" value={usd(cost?.net_savings_usd)} note={t.stt_audio_min != null ? `${fmt(t.stt_audio_min, 1)} min of speech transcribed` : undefined} />
    </dl>
    {a && <ul className="telemetry-assumptions">
      <li>Electricity {usd(a.electricity_usd_per_kwh)} per kWh{src("electricity_usd_per_kwh")}.</li>
      <li>Cloud text model {usd(a.cloud_llm_usd_per_1m_in)} per million input tokens{src("cloud_llm_usd_per_1m_in")}, {usd(a.cloud_llm_usd_per_1m_out)} per million output tokens{src("cloud_llm_usd_per_1m_out")}.</li>
      <li>Cloud speech to text {usd(a.cloud_stt_usd_per_min)} per minute{src("cloud_stt_usd_per_min")}.</li>
      {a.energy_scope && <li>Energy: {a.energy_scope}.</li>}
    </ul>}
    <p className="telemetry-note" role="status">{failed && at ? `The box did not answer the last check. Showing ${clockTime(at)}.`
      : at ? `Updated ${clockTime(at)} · every 5 seconds` : ""}</p>
  </div>;
}
