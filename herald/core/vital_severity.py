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

    def __init__(self, bands_by_key: dict[str, list[dict[str, Any]]]):
        self._bands = bands_by_key

    @classmethod
    def from_config(cls, loader, rel: str = "vital_ranges.yaml") -> "VitalRanges":
        cfg = loader(rel) or {}
        vitals = cfg.get("vitals") or {}
        return cls({key: (spec.get("bands") or []) for key, spec in vitals.items()})

    def keys(self) -> list[str]:
        return list(self._bands)

    def severity(self, key: str, value: Any) -> Optional[Severity]:
        """The severity band for a value, or None. `normal` bands exist in config to pin the boundaries in tests and
        to make a mid-range value explicit; they return None here, because normal gets no colour."""
        bands = self._bands.get(key)
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
