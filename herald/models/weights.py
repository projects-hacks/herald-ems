"""Model weights on this box. Loading by folder path means no library contacts a model hub at startup: the ambulance
has no link, and a hub check there stalls until it times out (live test 2026-09-24 found one on every start)."""
from __future__ import annotations

from pathlib import Path


def local_weights(model_id: str, offline: bool = True) -> str:
    """A model id (or a folder) -> the folder holding its weights. With `offline`, a model that isn't on this box
    is an error that says how to fetch it, never a silent download."""
    if Path(model_id).is_dir():
        return model_id
    if not offline:
        return model_id
    from huggingface_hub import snapshot_download
    try:
        return snapshot_download(model_id, local_files_only=True)
    except Exception as e:
        raise RuntimeError(f"{model_id} is not on this box: fetch it once with `hf download {model_id}` "
                           "(or set HERALD_MODELS_OFFLINE=0)") from e
