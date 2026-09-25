"""Absolute clinical severity for a vital value (config/vital_ranges.yaml).

A display and triage-attention aid, never a diagnosis and never a treatment recommendation (AGENTS.md invariant 3):
it says where a value sits, so an abnormal-but-steady reading shows as abnormal on the screen instead of only a
changing one. The medic decides.

Deterministic and data-driven: the bands are content in config/vital_ranges.yaml, this module is only the engine that
reads them, exactly like the score scales (herald/scoring) read config/scores/*.yaml. A new vital or a changed band is
a config edit, never a code edit. `core` has no I/O, so the YAML is loaded once at the composition root and handed in.
"""
from __future__ import annotations

from typing import Any, Optional

Severity = str  # "abnormal" | "critical"; a value that matches no coloured band has no severity (None)


class VitalRanges:
    """Maps a vital key and value to a severity band. Values that are missing, non-numeric or belong to a key with no
    bands (e.g. diastolic BP, deliberately un-coloured) return None: the tile stays its neutral category colour."""

    def __init__(self, bands_by_key: dict[str, list[dict[str, Any]]],
                 alt_bands_by_key: Optional[dict[str, dict[str, list[dict[str, Any]]]]] = None):
        self._bands = bands_by_key
        # Alternate band sets selected by patient context, e.g. SpO2 scale 2 for hypercapnic patients:
        # {"vitals.spo2": {"scale_2_bands": [...]}}. Empty when a key has only its default bands.
        self._alt = alt_bands_by_key or {}

    @classmethod
    def from_config(cls, loader, rel: str = "vital_ranges.yaml") -> "VitalRanges":
        cfg = loader(rel) or {}
        vitals = cfg.get("vitals") or {}
        bands = {key: (spec.get("bands") or []) for key, spec in vitals.items()}
        # Any spec key ending in `_bands` other than the default `bands` is an alternate set (scale_2_bands, ...).
        alt = {key: {name: rows for name, rows in spec.items() if name.endswith("_bands") and name != "bands"}
               for key, spec in vitals.items()
               if any(n.endswith("_bands") and n != "bands" for n in spec)}
        return cls(bands, alt)

    def keys(self) -> list[str]:
        return list(self._bands)

    def severity(self, key: str, value: Any, *, applicable: bool = True, spo2_scale: int = 1) -> Optional[Severity]:
        """The severity band for a value, or None. `normal` bands exist in config to pin the boundaries in tests and
        to make a mid-range value explicit; they return None here, because normal gets no colour.

        `applicable` is the scope gate. These bands are derived from the adult NEWS2 chart (config/vital_ranges.yaml),
        which RCP does not validate for children or documented pregnancy, and which uses a different SpO2 target for
        hypercapnic (scale-2) patients. Herald already withdraws the NEWS2 SCORE for exactly those patients
        (config/scores/news2.yaml applicability); this colouring is derived from the same chart, so it withdraws with
        it. When `applicable` is False the value shows in the neutral colour with no severity word, because a red or
        amber tuned to adult ranges would be actively wrong for that patient -- a paediatric HR of 120 is normal, a
        COPD target SpO2 of 90 is on target. Silence is the safe failure; a wrong colour is not. The caller passes
        whether the NEWS2 applicability for this patient is anything other than 'excluded'."""
        if not applicable:
            return None
        bands = self._bands.get(key)
        # SpO2 scale 2 (hypercapnic / COPD, target 88-92%) re-bands SpO2 so an on-target 90% is not flagged and a
        # normal 97% is. Selected only when the medic has set patient.spo2_scale to 2 (RCP: clinician direction
        # only); any other key or scale falls through to the default bands above.
        if spo2_scale == 2 and key == "vitals.spo2":
            bands = self._alt.get(key, {}).get("scale_2_bands") or bands
        if not bands:
            return None
        try:
            v = float(value)
        except (TypeError, ValueError):
            return None            # a vital that is not a plain number (a string, None) is never coloured
        if v != v:                 # NaN
            return None
        for band in bands:
            if self._matches(band, v):
                sev = band.get("severity", "normal")
                return sev if sev in ("abnormal", "critical") else None
        return None

    @staticmethod
    def _matches(band: dict[str, Any], v: float) -> bool:
        # Exactly the four forms documented in config/vital_ranges.yaml. `from` is inclusive, `to` exclusive, so
        # adjacent bands meet without overlap or gap and every boundary lands in exactly one band.
        if "below" in band:
            return v < band["below"]
        if "at_or_below" in band:
            return v <= band["at_or_below"]
        if "at_or_above" in band:
            return v >= band["at_or_above"]
        if "from" in band and "to" in band:
            return band["from"] <= v < band["to"]
        return False
