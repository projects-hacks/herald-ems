"""Reports built from the patient picture: the written handoff (MIST / SBAR) read to the receiving team.

Deterministic projections of confirmed facts and computed scores through templates in config/handoff.yaml. No
model writes report text, and nothing in a report is a recommendation.
"""
from .config import HandoffConfig, default_handoff_config
from .handoff import HandoffBuilder
from .lines import LINE_KINDS, Line

__all__ = ["HandoffBuilder", "HandoffConfig", "LINE_KINDS", "Line", "default_handoff_config"]
