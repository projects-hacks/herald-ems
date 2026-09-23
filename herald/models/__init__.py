"""Adapters to the local model servers: text/vision LLM (ZRT/vLLM), speech-to-text (Whisper)."""
from .llm_client import LocalLLMClient, salvage
from .stt import WhisperSTT
from .vision import VisionReader

__all__ = ["LocalLLMClient", "VisionReader", "WhisperSTT", "salvage"]
