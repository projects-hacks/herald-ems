"""Speech text -> candidate facts. Every extractor implements core.ports.Extractor."""
from .grounding import Grounding
from .guard import InstructionGuard, instruction_shaped
from .model import ModelExtractor, Prompts
from .pipeline import ExtractionPipeline, merge_model_facts
from .rules import RulesExtractor

__all__ = ["ExtractionPipeline", "Grounding", "InstructionGuard", "ModelExtractor", "Prompts", "RulesExtractor",
           "instruction_shaped", "merge_model_facts"]
