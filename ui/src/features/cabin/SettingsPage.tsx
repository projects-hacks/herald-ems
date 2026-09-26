// Settings: only what a medic sets for themselves, plus what this vehicle is running. Theme and Patients are not here:
// both are one tap in the header. The guided demo and the detailed (explain) view are presenter tools; they stay on
// the presenter bar (` key), Shift+P / Shift+E and ?present=1 / ?mode=explain, so a tap here cannot take a medic off
// the cabin screen mid-call (owner, 2026-09-26).
import { useHerald } from "@/lib/store";
import type { TypeScale } from "@/lib/store";

const SCALES: TypeScale[] = [1, 1.25, 1.5];

function day(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function SettingsPage() {
  const ui = useHerald((st) => st.ui);
  const setUi = useHerald((st) => st.setUi);
  const s = useHerald((st) => st.snapshot);
  const protocols = s?.protocols;
  return (
    <div className="cabin-settings workspace-page-surface">
      <h1 className="workspace-page-heading">Settings</h1>

      <section aria-labelledby="settings-display">
        <h2 id="settings-display" className="cabin-settings-heading">Display</h2>
        <div className="cabin-actions" role="group" aria-label="Text size">
          {SCALES.map((scale) => <button className="cabin-button" key={scale} aria-pressed={ui.typeScale === scale}
            onClick={() => setUi({ typeScale: scale })}>Text {scale * 100}%</button>)}
        </div>
        <label className="copilot-switch"><input type="checkbox" checked={ui.reducedMotion} onChange={(e) => setUi({ reducedMotion: e.target.checked })} />
          Reduce motion</label>
      </section>

      <section aria-labelledby="settings-capture">
        <h2 id="settings-capture" className="cabin-settings-heading">Capture</h2>
        <label className="copilot-switch"><input type="checkbox" checked={ui.autoCapture} onChange={(e) => setUi({ autoCapture: e.target.checked, capturePaused: !e.target.checked })} />
          Listen and watch automatically when a call starts</label>
        <p className="cabin-settings-note">Off: each call starts paused until you tap to listen and watch.</p>
      </section>

      <section aria-labelledby="settings-privacy">
        <h2 id="settings-privacy" className="cabin-settings-heading">Recording and privacy</h2>
        <ul className="cabin-settings-list">
          <li>Record only where your service allows it. While Herald listens and watches, speech (cut at natural pauses) and useful camera stills go to this vehicle’s server and are processed there, not in the cloud.</li>
          <li>Nothing Herald hears or reads counts toward a score, or goes to the ED, until you confirm it. The ED receives it only after you authorize the handoff.</li>
          <li>Pausing, changing patient or leaving this page stops capture. If the vehicle server can’t be reached, speech waits here for about a minute and is retried; after that the oldest words are dropped and Herald says so.</li>
          <li>“Delivered” means the ED’s system received the update, not that a clinician has read it.</li>
        </ul>
      </section>

      {s && <section aria-labelledby="settings-vehicle">
        <h2 id="settings-vehicle" className="cabin-settings-heading">This vehicle</h2>
        <dl className="cabin-settings-facts">
          <div><dt>County protocols</dt><dd>{s.county.name}{protocols && <>{` · ${protocols.sections} sections`}{protocols.last_sync ? ` · updated ${day(protocols.last_sync)}` : ""}</>}</dd></div>
          <div><dt>Cloud AI calls</dt><dd className="num">{s.counters.cloud_ai_calls}</dd></div>
        </dl>
      </section>}

      <p className="cabin-muted">Prototype. Not validated for use during patient care.</p>
    </div>
  );
}
