"""Local text embeddings for retrieval (a Hugging Face encoder, CLS pooling, L2-normalized)."""
from __future__ import annotations

import threading
from typing import Optional

import numpy as np

from .weights import local_weights


class HFEmbedder:
    """The `Embedder` interface. Loads on first use."""

    def __init__(self, model_id: str, query_prefix: str = "", device: str = "cpu", offline: bool = True):
        self.model_id, self.query_prefix, self.device, self.offline = model_id, query_prefix, device, offline
        self._tok = self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                from transformers import AutoModel, AutoTokenizer
                path = local_weights(self.model_id, self.offline)
                self._tok = AutoTokenizer.from_pretrained(path)
                self._model = AutoModel.from_pretrained(path).to(self.device).eval()

    def embed(self, texts: list[str], query: bool = False, batch: int = 32) -> np.ndarray:
        import torch
        self._load()
        texts = [self.query_prefix + t if query else t for t in texts]
        out = []
        with torch.no_grad():
            for i in range(0, len(texts), batch):
                enc = self._tok(texts[i:i + batch], padding=True, truncation=True, max_length=512, return_tensors="pt")
                enc = {k: v.to(self.device) for k, v in enc.items()}
                cls = self._model(**enc).last_hidden_state[:, 0]
                out.append(torch.nn.functional.normalize(cls, dim=-1).cpu().numpy())
        return np.concatenate(out) if out else np.zeros((0, 1), dtype=np.float32)
