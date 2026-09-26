"""Config-driven intents from structured facts, never phrase matching."""
from .types import CaptureIntent, IncidentEvent


class CapturePolicy:
    def __init__(self, config: dict):
        self.config = config
        self.once = set()
        self.last_monitor = float("-inf")
        self.stable = 0

    def reset(self):
        self.once.clear()
        self.last_monitor = float("-inf")
        self.stable = 0

    def on_event(self, event: IncidentEvent) -> list[CaptureIntent]:
        out = []
        for index, rule in enumerate(self.config["triggers"]):
            kind = "facts_added" if rule["on"] == "fact" else rule["on"]
            if kind != event.kind or index in self.once:
                continue
            if set(self.config["suppress_during"]) & event.states and not (rule["purpose"] == "record" and rule["mode"] == "monitor"):
                continue
            facts = [f for f in event.facts if f.key == rule.get("key")] if kind == "facts_added" else [None]
            for fact in facts:
                if fact and any(not isinstance(fact.value, dict) or fact.value.get(k) != v for k, v in rule.get("where", {}).items()):
                    continue
                if kind == "eta_changed":
                    eta = event.summary_diff.get("eta_min")
                    if not isinstance(eta, (int, float)) or isinstance(eta, bool) or not 0 <= eta <= rule["when"]["lte"]:
                        continue
                trigger = f"speech:{fact.key}" if fact else kind
                out.append(CaptureIntent(trigger, rule["mode"], rule["window_s"],
                                         "monitor" if rule["mode"] == "monitor" else None,
                                         rule["purpose"], fact.id if fact else None, rule["reason"]))
                if rule.get("once"):
                    self.once.add(index)
        return out

    def interval(self, speech_recent: bool) -> float:
        """Seconds between monitor reads: `min_interval_s` in a quiet cabin, `speech_interval_s` while speech is being
        processed, so a read competes with the extraction model only when nobody is talking (config/capture.yaml)."""
        m = self.config["monitor"]
        return m["speech_interval_s"] if speech_recent else m["min_interval_s"]

    def on_tick(self, now: float, gate_state: dict) -> list[CaptureIntent]:
        m = self.config["monitor"]
        if not gate_state.get("roi") or not gate_state.get("usable"):
            self.stable = 0
            return []
        self.stable = self.stable + 1 if gate_state.get("stable", True) else 1
        elapsed = now - self.last_monitor
        interval = self.interval(bool(gate_state.get("speech_recent")))
        if self.stable < m["stable_frames"] or elapsed < interval:
            return []
        # An unchanged picture still gets a periodic point, so the trend stays current.
        if not gate_state.get("changed") and elapsed < max(m["max_interval_s"], interval):
            return []
        trigger = "monitor_changed" if gate_state.get("changed") else "monitor_refresh"
        return [CaptureIntent(trigger, "monitor", self.config["buffer_s"], "monitor", reason=self.config["reasons"][trigger])]

    def captured(self, intent: CaptureIntent, now: float):
        if intent.mode == "monitor":
            self.last_monitor = now
