"""Speech text -> candidate facts, by the local model (herald/extraction/model.py), with per-fact confidence from
token probabilities, grounding, and prompt-injection detection. There is no regex extraction in the product."""
from .grounding import Grounding
from .guard import InstructionGuard, instruction_shaped
from .model import ModelExtractor, Prompts

__all__ = ["Grounding", "InstructionGuard", "ModelExtractor", "Prompts", "instruction_shaped"]
