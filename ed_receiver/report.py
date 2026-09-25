"""Read-aloud projection of received confirmed data only; no vehicle/model connection."""
from datetime import datetime
from zoneinfo import ZoneInfo
from herald.config import Settings, load_yaml
from herald.config.county import CountyRegistry

from herald.core.incident import Incident
from herald.core.schema import FactIn, Status
from herald.core.snapshot import build_projector
from herald.core.vocabulary import default_vocabulary
from herald.reporting import HandoffBuilder, default_handoff_config
from herald.scoring import default_scales


def received_report(patient_id: str, received: dict, format_id=None) -> dict:
    vocab = default_vocabulary()
    display = load_yaml("ed_display.yaml")
    settings = Settings.from_env({"HERALD_COUNTY": display["report_county"], "HERALD_TZ": display["report_timezone"]})
    incident = Incident(vocabulary=vocab, projector=build_projector(settings, CountyRegistry(settings.county)))
    incident.id = patient_id
    incident.started = datetime.fromisoformat(received["first_at"])
    # Full packets contain event history; later critical packets can supersede those latest values.
    rows = list(received["timeline"])
    latest = {row["k"]: row["v"] for row in rows}
    rows += [{"k": key, "v": value["v"], "t": value["t"]} for key, value in received["fields"].items()
             if key not in latest or latest[key] != value["v"]]
    for row in rows:
        if row["k"] not in vocab.keys:
            continue  # Unknown and derived fields remain visible in the ED field list, never guessed.
        try:
            timestamp = datetime.fromisoformat(row["t"])
            fact = incident.ingest(FactIn(key=row["k"], value=row["v"], captured_by="device", role="device",
                                          speaker="received confirmed relay", confidence=1,
                                          provenance={"observed_at": row.get("o")}), record=False)
            fact.ts = timestamp
            fact.status = Status.confirmed
        except (ValueError, TypeError):
            continue
    incident.commit()
    builder = HandoffBuilder(default_handoff_config(), vocab, default_scales(), ZoneInfo(settings.timezone))
    report = builder.build(incident, format_id)
    report["scope"] = "Received confirmed data only; may lag the vehicle. Dispatch, vehicle county and timezone were not transmitted. Generic published scales only; timestamps use UTC."
    return report
