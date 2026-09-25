# Herald app container: FastAPI backend + STT/embedding model code. Runs on the ZGX Nano (aarch64, GB10, CUDA 13).
#
# What this DOES NOT contain: ZRT (the vLLM wrapper that serves the extraction LLM and the vision model) and the
# fine-tuned/vision model weights. Those stay on the host:
#   - ZRT is an HP snap tied to the host's driver and GPU, not a pip/pypi package. `sudo zrt setup --mode system`
#     is a one-time host operation (AGENTS.md), not something a container should redo per build.
#   - The private model repos need ~/.config/herald/secrets.env (HF_TOKEN) and take 3-23 minutes to warm up;
#     starting them is a deliberate, GPU-exclusive action the team coordinates on, not a container side effect.
# This container reaches ZRT at http://127.0.0.1:8080 over `network_mode: host` (see docker-compose.yml), exactly
# like a non-containerized `scripts/run_dev.sh` would, and it is why HERALD_LLM_URL must stay a loopback address
# (herald/config/settings.py enforces this).
#
# torch/torchaudio/transformers are installed from PyPI here (verified working with CUDA on GB10/sm_121 as of
# torch 2.11+: https://pytorch.org/blog/vllm-and-pytorch-work-together-to-improve-the-developer-experience-on-aarch64/),
# NOT from the host's `zgx` conda env. That env is a snapshot of a specific, hand-tuned install (AGENTS.md
# pitfalls); this image is independently reproducible from a clean clone, which is the point of containerizing it.
FROM nvidia/cuda:13.0.1-base-ubuntu24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3.12 python3.12-venv libsndfile1 curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN python3.12 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
# torch/torchaudio pinned separately: they need PyTorch's own CUDA 13.0 wheel index, not plain PyPI.
RUN pip install --no-cache-dir torch==2.14.0 torchaudio==2.11.0 \
      --extra-index-url https://download.pytorch.org/whl/cu130 \
    && pip install --no-cache-dir "transformers>=5.17" -r requirements.txt

COPY herald/ herald/
COPY config/ config/
COPY web/ web/
COPY scripts/run_dev.sh scripts/run_dev.sh
COPY ui/dist/ ui/dist/
# Build ui/dist before building this image: (cd ui && npm ci && npm run build), or
# docker compose --profile ui-build run --rm ui-build. It is required build output,
# not committed source. The compose volume allows rebuilding it without rebuilding Python.

ENV HERALD_MODELS_OFFLINE=1 \
    HERALD_LLM_URL=http://127.0.0.1:8080/v1 \
    PORT=8100
EXPOSE 8100

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -sf "http://127.0.0.1:${PORT}/api/health" || exit 1

CMD ["sh", "-c", "python -m uvicorn herald.app:app --host 0.0.0.0 --port ${PORT}"]
