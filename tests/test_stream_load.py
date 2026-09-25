"""The streaming loader must produce the same model as `from_pretrained`.

`from_pretrained` transiently needs about twice the checkpoint on the GB10 (unified memory makes the mmapped shards
count as GPU memory while the host fills with resident pages), which killed two 30B loads on 2026-09-25. The
streaming loader in scripts/lora_common.py holds one shard at a time instead. It is only safe to use if it builds a
bit-for-bit equivalent model, and the risky part is layout: Qwen3-VL-MoE stores its fused experts transposed on
disk, so a loader that assigns tensors as they come installs silently wrong weights.

These tests run on the CPU (`device="cpu"`), so they need no GPU and can run next to a training job.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from lora_common import _fit_to_target, _shard_files, hf_snapshot, stream_load_model  # noqa: E402

SMALL = "Qwen/Qwen3-VL-2B-Instruct"       # on this box; the 30B is the same architecture family


# ---------------------------------------------------------------- shape fitting (no model needed)


def test_a_matching_shape_is_passed_through():
    torch = pytest.importorskip("torch")
    t = torch.zeros(4, 5)
    assert _fit_to_target("w", t, torch.zeros(4, 5)) is t


def test_a_transposed_fused_expert_is_swapped_back():
    """On disk: (experts, in, out). In the model: (experts, out, in)."""
    torch = pytest.importorskip("torch")
    disk = torch.arange(2 * 3 * 4, dtype=torch.float32).reshape(2, 3, 4)      # (E, 3, 4)
    target = torch.zeros(2, 4, 3)                                            # (E, 4, 3)
    out = _fit_to_target("experts.gate_up_proj", disk, target)
    assert tuple(out.shape) == (2, 4, 3)
    assert out.is_contiguous()
    assert torch.equal(out, disk.transpose(-2, -1))                           # the values, not just the shape


def test_an_unfittable_shape_raises_instead_of_guessing():
    torch = pytest.importorskip("torch")
    with pytest.raises(RuntimeError, match="does not fit"):
        _fit_to_target("w", torch.zeros(4, 5), torch.zeros(7, 9))


def test_a_tensor_the_model_does_not_have_is_passed_through():
    torch = pytest.importorskip("torch")
    t = torch.zeros(3)
    assert _fit_to_target("extra", t, None) is t


# ---------------------------------------------------------------- shard discovery


def test_shard_discovery_handles_sharded_and_single_file(tmp_path):
    (tmp_path / "model.safetensors").touch()
    assert [p.name for p in _shard_files(tmp_path)] == ["model.safetensors"]

    idx = tmp_path / "model.safetensors.index.json"
    idx.write_text(json.dumps({"weight_map": {"a": "model-00002-of-00002.safetensors",
                                              "b": "model-00001-of-00002.safetensors"}}))
    assert [p.name for p in _shard_files(tmp_path)] == ["model-00001-of-00002.safetensors",
                                                        "model-00002-of-00002.safetensors"]


def test_no_checkpoint_is_an_error(tmp_path):
    with pytest.raises(SystemExit):
        _shard_files(tmp_path)


# ---------------------------------------------------------------- the real equality check


@pytest.mark.slow
def test_streamed_model_matches_from_pretrained_on_real_inputs():
    """Same logits as `from_pretrained` on 3 inputs, within bf16 tolerance."""
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    if hf_snapshot(SMALL) is None:
        pytest.skip(f"{SMALL} is not in the local HF cache")

    from transformers import AutoModelForImageTextToText, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(SMALL)
    prompts = ["Vitals: BP 142/88, pulse 72.",
               "The patient's wife says he takes warfarin.",
               "Last known well was 13:40."]
    batches = [tok(p, return_tensors="pt") for p in prompts]

    streamed = stream_load_model(SMALL, device="cpu", dtype=torch.bfloat16, progress=False, drop_cache=False)
    streamed.eval()
    with torch.no_grad():
        got = [streamed(**b).logits.float() for b in batches]
    del streamed

    reference = AutoModelForImageTextToText.from_pretrained(SMALL, dtype=torch.bfloat16,
                                                           attn_implementation="sdpa")
    reference.eval()
    with torch.no_grad():
        want = [reference(**b).logits.float() for b in batches]
    del reference

    for i, (g, w) in enumerate(zip(got, want)):
        assert g.shape == w.shape, f"input {i}: {g.shape} != {w.shape}"
        # bf16 has ~3 decimal digits; compare on the distribution the model actually produces
        assert torch.allclose(g, w, atol=2e-2, rtol=1e-2), \
            f"input {i}: max abs diff {(g - w).abs().max().item()}"
        assert g.argmax(-1).equal(w.argmax(-1)), f"input {i}: different argmax token"


@pytest.mark.slow
def test_streamed_model_leaves_nothing_on_meta():
    torch = pytest.importorskip("torch")
    if hf_snapshot(SMALL) is None:
        pytest.skip(f"{SMALL} is not in the local HF cache")
    m = stream_load_model(SMALL, device="cpu", dtype=torch.bfloat16, progress=False, drop_cache=False)
    meta = [n for n, t in list(m.named_parameters()) + list(m.named_buffers()) if t.device.type == "meta"]
    assert meta == []


# ---------------------------------------------------------------- the memory sampler


def test_the_sampler_writes_flushed_rows_and_a_final_line(tmp_path):
    """Rows must be on disk within a second, because a hard freeze is exactly when the file has to be readable."""
    import time

    from lora_common import MemorySampler, summarize_memory

    path = tmp_path / "mem.jsonl"
    s = MemorySampler(path, hz=50.0, flush_every_s=0.05).start()
    time.sleep(0.5)
    mid = [l for l in path.read_text().splitlines() if l.strip()]
    assert len(mid) >= 5, "nothing was flushed while running"
    s.close()

    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    assert rows[-1].get("final") is True
    assert all("mem_available_gib" in r and "t" in r for r in rows)

    out = summarize_memory(path)
    assert out["samples"] == len(rows)
    assert out["min_mem_available_gib"] <= out["max_mem_available_gib"]


def test_summarize_survives_a_torn_last_line(tmp_path):
    """After a lockup the last line is usually half-written; the summary must still be readable."""
    from lora_common import summarize_memory

    path = tmp_path / "mem.jsonl"
    path.write_text('{"t": 1.0, "mem_available_gib": 100.0, "torch_max_allocated_gib": 10.0}\n'
                    '{"t": 2.0, "mem_available_gib": 20.0, "torch_max_allocated_gib": 40.0}\n'
                    '{"t": 3.0, "mem_avai')
    out = summarize_memory(path)
    assert out["samples"] == 2
    assert out["min_mem_available_gib"] == 20.0
    assert out["torch_max_allocated_gib"] == 40.0


def test_summarize_of_a_missing_or_empty_file_is_empty(tmp_path):
    from lora_common import summarize_memory

    path = tmp_path / "mem.jsonl"
    path.write_text("")
    assert summarize_memory(path) == {}
