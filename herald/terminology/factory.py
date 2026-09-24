"""Builds the drug coder from settings: the one recipe the app (composition root) and the benchmarks share, so a
benchmark codes drug names exactly as the running app does."""
from __future__ import annotations

import logging
from typing import Optional

from ..config import Settings
from ..core.ports import Normalizer
from ..core.vocabulary import Vocabulary
from .coding import MedicationCoder
from .rxnorm import RxNormNormalizer

log = logging.getLogger(__name__)


def build_coder(settings: Settings, vocabulary: Vocabulary,
                normalizer: Optional[Normalizer] = None) -> Optional[MedicationCoder]:
    """RxNorm coding for drug and allergen names, or None when it is switched off or the index isn't built.
    Tests inject a small in-memory normalizer."""
    if normalizer is None and settings.terminology:
        if settings.terminology_index.exists():
            normalizer = RxNormNormalizer.load(settings.terminology_index)
        else:
            log.warning("RxNorm index %s is missing: drug names stay as said and nothing is coded. "
                        "Build it with scripts/build_rxnorm_index.py", settings.terminology_index)
    return MedicationCoder.from_config(normalizer, vocabulary) if normalizer is not None else None
