"""The registry of handoff line kinds (config/handoff.yaml `kind`). A new kind is a class added here."""
from __future__ import annotations

from .lines import EventsLine, FactLine
from .score_line import ScoreLine
from .trend_line import TrendsLine

LINE_KINDS = {"fact": FactLine(), "events": EventsLine(), "score": ScoreLine(), "trends": TrendsLine()}
