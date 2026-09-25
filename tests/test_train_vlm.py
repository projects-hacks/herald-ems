"""Run F trainer, data and merge (scripts/train_vlm_lora.py, vlm_data.py, merge_vlm_lora.py, build_replay_set.py).
CPU only. Tests that need the Qwen3-VL processor files use the local HF cache and are skipped without it."""
import json
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import vlm_data as vd  # noqa: E402
from lora_common import hf_snapshot  # noqa: E402

BASE = "Qwen/Qwen3-VL-30B-A3B-Instruct"


@pytest.fixture(scope="module")
def cfg():
    from herald.config import load_yaml

    return load_yaml("training.yaml")["herald-f"]


@pytest.fixture(scope="module")
def processor():
    snap = hf_snapshot(BASE)
    if snap is None or not (snap / "tokenizer.json").exists():
        pytest.skip("Qwen3-VL processor files not in the local HF cache")
    from transformers import AutoProcessor

    return AutoProcessor.from_pretrained(str(snap))


@pytest.fixture(scope="module")
def enc(processor, cfg):
    return vd.Encoder(processor, cfg["image"]["max_pixels"], cfg["image"]["min_pixels"])


def _photo(tmp_path, size=(640, 480)):
    from PIL import Image

    p = tmp_path / "p.jpg"
    Image.new("RGB", size, (200, 30, 30)).save(p)
    return p


# ---------- config ----------
def test_config_block(cfg):
    for k in ("base", "label", "merged_repo_suffix", "data", "mix", "lora", "optim", "batching", "image", "replay"):
        assert k in cfg
    assert cfg["mix"]["epochs"] >= 1 and 0.05 <= cfg["mix"]["replay_share"] <= 0.10     # TRAINING_PLAN §4.4
    if cfg["lora"]["target_parameters"]:
        assert cfg["lora"]["dropout"] == 0.0            # PEFT's parameter LoRA refuses dropout
    assert "visual" not in cfg["lora"]["target_modules"] and "language_model" in cfg["lora"]["target_modules"]
    assert cfg["image"]["min_pixels"] < cfg["image"]["max_pixels"]


def test_served_label_has_extraction_profile(cfg):
    from herald.extraction.profiles import default_profiles

    assert default_profiles().for_label(cfg["label"]) is not None


def test_train_lora_keeps_its_helpers():
    import train_lora

    assert train_lora.system_prompt("ems-e") and callable(train_lora.reclaim_unified_memory)


# ---------- rows ----------
def test_row_shapes(tmp_path):
    img = _photo(tmp_path)
    vis = {"system": "S", "modes": {"monitor": "read the monitor"}}
    a = vd.from_record({"messages": [{"role": "system", "content": "sys"}, {"role": "user", "content": "u"},
                                     {"role": "assistant", "content": "{\"f\":[]}"}]}, "text", tmp_path)
    b = vd.from_record({"system": "sys", "user": "u", "assistant": "{}"}, "text", tmp_path)
    c = vd.from_record({"text": "[dispatch: fall]\nu", "completion": "{}"}, "text", tmp_path, default_system="P")
    d = vd.from_record({"image": img.name, "mode": "monitor", "target": {"facts": [{"key": "k", "value": 1}]}},
                       "image", tmp_path, vision_prompts=vis)
    e = vd.from_record({"messages": [{"role": "system", "content": "S"},
                                     {"role": "user", "content": [{"type": "text", "text": "t"},
                                                                  {"type": "image", "image": str(img)}]},
                                     {"role": "assistant", "content": "{}"}]}, "replay", tmp_path)
    assert (a.system, a.user, a.image) == ("sys", "u", None) and b.system == "sys" and c.system == "P"
    assert d.system == "S" and d.user == "read the monitor" and d.image == img and d.task == "monitor"
    assert d.assistant == '{"facts":[{"key":"k","value":1}]}'                  # compact JSON target
    assert e.image == img and e.user == "t"
    with pytest.raises(ValueError):
        vd.from_record({"text": "x", "completion": "{}"}, "text", tmp_path)   # no system prompt anywhere


def test_messages_mirror_llm_client(tmp_path):
    """Text first, then the image; a text-only row sends a plain string (llm_client.chat_json)."""
    ex = vd.Example("image", "S", "U", "{}", _photo(tmp_path))
    assert ex.messages()[1]["content"] == [{"type": "text", "text": "U"}, {"type": "image"}]
    assert vd.Example("text", "S", "U", "{}").messages()[1]["content"] == "U"


def test_prompt_drift_is_caught():
    rows = [vd.Example("text", "old prompt", "u", "{}", task="extract"), vd.Example("text", "P", "u", "{}")]
    assert vd.prompt_drift(rows, {"system:text": {"P"}}) == {"extract": 1}


# ---------- mix and batches ----------
def test_mix_ratio_and_fresh_photos():
    text, image, replay = [f"t{i}" for i in range(900)], [f"i{i}" for i in range(500)], [f"r{i}" for i in range(400)]
    epochs = vd.mix_epochs(text, image, replay, {"epochs": 2, "image_rows_per_epoch": 300, "replay_share": 0.075,
                                                 "seed": 1})
    for rows in epochs:
        n_rep = sum(r.startswith("r") for r in rows)
        assert sum(r.startswith("t") for r in rows) == 900 and sum(r.startswith("i") for r in rows) == 300
        assert abs(n_rep / len(rows) - 0.075) < 0.002
        assert len({r for r in rows if r.startswith("i")}) == 300          # no photo twice in an epoch
    few = vd.mix_epochs(text, image, replay[:10], {"epochs": 1, "image_rows_per_epoch": 9999, "replay_share": 0.075})
    assert sum(r.startswith("r") for r in few[0]) == 10 and sum(r.startswith("i") for r in few[0]) == 500
    e1, e2 = ({r for r in rows if r.startswith("i")} for rows in epochs)
    assert len(e1 | e2) == 500 and len(e1 & e2) == 100          # every photo before any repeats


def test_plan_batches_budget_and_accum():
    rng = random.Random(0)
    lengths = [rng.choice([150, 200, 900, 1100, 2300]) for _ in range(997)]
    bs = vd.plan_batches(lengths, 8192, 24, 2, random.Random(1))
    assert len(bs) % 2 == 0
    assert sorted(i for b in bs for i in b) == list(range(997))
    assert all(len(b) * max(lengths[i] for i in b) <= 8192 and len(b) <= 24 for b in bs)
    assert vd.steps_for([10, 12], 2) == [5, 11]


def test_collate_pads_and_masks():
    import torch

    f = [{"input_ids": [1, 2, 3], "labels": [-100, 2, 3]},
         {"input_ids": [4, 5], "labels": [-100, 5], "pixel_values": torch.ones(4, 3), "image_grid_thw": torch.tensor([[1, 2, 2]])}]
    b = vd.collate(f, 0)
    assert b["input_ids"].tolist() == [[1, 2, 3], [4, 5, 0]] and b["labels"][1].tolist() == [-100, 5, -100]
    assert b["attention_mask"].tolist() == [[1, 1, 1], [1, 1, 0]] and b["pixel_values"].shape == (4, 3)


# ---------- encoding with the real processor ----------
def test_prompt_identical_to_llm_client_request(enc, monkeypatch, tmp_path):
    """Capture the body llm_client posts, turn it into what vLLM hands the chat template (image_url -> image, in
    place), render it with the model's template, and compare with the training prompt byte for byte."""
    import base64

    import httpx

    from herald.models.llm_client import LocalLLMClient

    sent = {}

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(httpx, "post", lambda url, json, timeout: sent.update(json) or R())
    img = _photo(tmp_path)
    client = LocalLLMClient("http://127.0.0.1:8080/v1", model="herald-f")
    for image in (None, img):
        client.chat_json("SYS", "USER line", image_b64=base64.b64encode(img.read_bytes()).decode() if image else None)
        assert sent["chat_template_kwargs"] == {"enable_thinking": False}
        msgs = [{**m, "content": [({"type": "image"} if p["type"] == "image_url" else p) for p in m["content"]]}
                if isinstance(m["content"], list) else m for m in sent["messages"]]
        served = enc.tok.apply_chat_template(msgs, chat_template=enc.template, tokenize=False,
                                             add_generation_prompt=True, **sent["chat_template_kwargs"])
        assert served == enc.prompt_text(vd.Example("x", "SYS", "USER line", "{}", image))


def test_loss_mask_covers_only_the_answer(enc):
    ex = vd.Example("text", "SYS", "[dispatch: fall]\nBP 120 over 80", '{"f":[["vitals.sbp",120,"m"]]}')
    out = enc.encode(ex)
    labeled = [t for t, l in zip(out["input_ids"], out["labels"]) if l != -100]
    first = next(i for i, l in enumerate(out["labels"]) if l != -100)
    assert all(l == -100 for l in out["labels"][:first]) and out["labels"][first:] == out["input_ids"][first:]
    assert enc.tok.decode(labeled) == ex.assistant + vd.END
    assert enc.tok.decode(out["input_ids"][:first]).endswith("<|im_start|>assistant\n")
    assert len(out["input_ids"]) == enc.length(ex)


def test_image_row_tokens_and_bound(enc, tmp_path, cfg):
    ex = vd.Example("image", "SYS", "read it", "{}", _photo(tmp_path, (4000, 3000)))   # a 12 MP phone photo
    out = enc.encode(ex)
    pad = enc.tok.convert_tokens_to_ids("<|image_pad|>")
    n_img = sum(t == pad for t in out["input_ids"])
    grid = out["image_grid_thw"][0].tolist()
    assert n_img == grid[0] * grid[1] * grid[2] // 4 and n_img * 1024 <= cfg["image"]["max_pixels"]
    assert len(out["input_ids"]) == enc.length(ex)
    assert all(l == -100 for t, l in zip(out["input_ids"], out["labels"]) if t == pad)
    from PIL import Image

    ref = enc.processor(text=[enc.prompt_text(ex)], images=[Image.open(ex.image).convert("RGB")], return_tensors="pt",
                        return_mm_token_type_ids=True)          # M-RoPE needs the processor's image-token map
    n = ref["input_ids"].shape[1]
    assert out["mm_token_type_ids"][:n] == ref["mm_token_type_ids"][0].tolist() and not any(out["mm_token_type_ids"][n:])


# ---------- merge ----------
def _tiny(tmp_path):
    import torch
    from transformers import Qwen3VLMoeConfig, Qwen3VLMoeForConditionalGeneration

    cfg = Qwen3VLMoeConfig(
        text_config=dict(hidden_size=48, intermediate_size=96, moe_intermediate_size=40, num_experts=4,
                         num_experts_per_tok=2, num_hidden_layers=2, num_attention_heads=4, num_key_value_heads=2,
                         head_dim=12, vocab_size=128,
                         rope_scaling={"rope_type": "default", "mrope_section": [2, 2, 2], "mrope_interleaved": True}),
        vision_config=dict(depth=1, hidden_size=32, intermediate_size=64, num_heads=2, out_hidden_size=48,
                           deepstack_visual_indexes=[0]))
    torch.manual_seed(0)
    m = Qwen3VLMoeForConditionalGeneration(cfg).eval()
    m.save_pretrained(tmp_path / "base")
    return m


def test_streaming_merge_matches_peft(tmp_path, cfg):
    """Expert (target_parameters) and attention LoRA merged shard by shard equal PEFT's own forward, and the merged
    checkpoint keeps the base's tensor names, shapes and on-disk layout."""
    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import Qwen3VLMoeForConditionalGeneration

    import merge_vlm_lora as mv

    m = _tiny(tmp_path)
    lc = cfg["lora"]
    pm = get_peft_model(m, LoraConfig(r=4, lora_alpha=8, lora_dropout=0.0, target_modules=lc["target_modules"],
                                      target_parameters=lc["target_parameters"]))
    with torch.no_grad():
        for n, p in pm.named_parameters():
            if "lora_" in n:
                p.normal_(0, 0.2)
    pm.save_pretrained(tmp_path / "adapter")
    ids = torch.randint(0, 128, (1, 12))
    with torch.no_grad():
        want = pm(input_ids=ids).logits
    mv.merge(tmp_path / "base", tmp_path / "adapter", tmp_path / "merged")
    mv.verify_layout(tmp_path / "base", tmp_path / "merged")
    merged = Qwen3VLMoeForConditionalGeneration.from_pretrained(tmp_path / "merged").eval()
    with torch.no_grad():
        got = merged(input_ids=ids).logits
    base = Qwen3VLMoeForConditionalGeneration.from_pretrained(tmp_path / "base").eval()
    with torch.no_grad():
        before = base(input_ids=ids).logits
    assert (want - before).abs().max() > 1e-2                # the adapter does change the model
    assert torch.allclose(got, want, atol=2e-4, rtol=1e-3)
    deltas, _ = mv.adapter_deltas(tmp_path / "adapter")
    assert {k.rsplit(".", 1)[-1] for k, v in deltas.items() if v[0] == "experts"} == {"gate_up_proj", "down_proj"}


# ---------- replay ----------
def test_replay_decontamination():
    from build_replay_set import Decontaminator

    d = Decontaminator(["What's the time window for calling a stroke alert?"])
    assert not d.clean("what's the time window for calling a stroke alert")      # the benchmark question
    assert d.clean("Which hospital takes a pregnant trauma patient over twenty weeks?")
    assert not d.clean("Which hospital takes a pregnant trauma patient over twenty weeks?")   # duplicate


# ---------- crash safety (MODEL_PLAN §0l "Crash safety") ----------
def _ckpt(out, step, complete=True, files=("adapter_model.safetensors", "optimizer.pt", "trainer_state.json")):
    import ckpt_safety

    d = out / f"checkpoint-{step}"
    d.mkdir(parents=True)
    for f in files:
        (d / f).write_bytes(b"x" * (10 + step))
    if complete:
        ckpt_safety.mark_complete(d, {"step": step})
    return d


def test_resume_picks_newest_complete_checkpoint(tmp_path):
    import ckpt_safety

    _ckpt(tmp_path, 10)
    _ckpt(tmp_path, 20)
    _ckpt(tmp_path, 30, complete=False)                       # killed mid-save: no marker
    assert ckpt_safety.prepare_resume(tmp_path) == tmp_path / "checkpoint-20"
    assert not (tmp_path / "checkpoint-30").exists()          # renamed aside, never deleted
    assert len(list(tmp_path.glob("incomplete-checkpoint-30-*"))) == 1
    assert [s for s, _ in ckpt_safety.checkpoints(tmp_path)] == [10, 20]


def test_marker_detects_truncated_or_missing_files(tmp_path):
    import ckpt_safety

    d = _ckpt(tmp_path, 40)
    assert ckpt_safety.is_complete(d)
    (d / "optimizer.pt").write_bytes(b"x")                    # truncated after the marker
    assert not ckpt_safety.is_complete(d)
    d2 = _ckpt(tmp_path, 50)
    (d2 / "trainer_state.json").unlink()
    assert not ckpt_safety.is_complete(d2)
    assert ckpt_safety.prepare_resume(tmp_path) is None


def test_no_checkpoint_means_fresh_start(tmp_path):
    import ckpt_safety

    assert ckpt_safety.prepare_resume(tmp_path) is None


def test_effective_batches_drop_work_redone_after_a_crash():
    import ckpt_safety

    lines = [json.dumps(x) for x in (
        {"segment_start": 0}, {"step": 0, "rows": [1]}, {"step": 1, "rows": [2]}, {"step": 2, "rows": [3]},
        {"step": 3, "rows": [4]},                                            # crashed; last checkpoint was step 2
        {"segment_start": 2}, {"step": 2, "rows": [3]}, {"step": 3, "rows": [4]}, {"step": 4, "rows": [5]})]
    assert [b["rows"] for b in ckpt_safety.effective_batches(lines)] == [[1], [2], [3], [4], [5]]


def test_plan_fingerprint_changes_with_data_or_order():
    import ckpt_safety

    rows = [("text", "a"), ("text", "b"), ("image", "c")]
    f = ckpt_safety.plan_fingerprint(rows, [[0, 1], [2]], {"steps": 1})
    assert f == ckpt_safety.plan_fingerprint(rows, [[0, 1], [2]], {"steps": 1})
    assert f != ckpt_safety.plan_fingerprint(rows, [[1, 0], [2]], {"steps": 1})
    assert f != ckpt_safety.plan_fingerprint(rows[:2] + [("image", "d")], [[0, 1], [2]], {"steps": 1})
    assert f != ckpt_safety.plan_fingerprint(rows, [[0, 1], [2]], {"steps": 2})


def test_resume_reapplies_the_configured_cadence(tmp_path):
    """A cadence change in config/training.yaml must actually take effect on a resume.

    transformers decides when to save and evaluate from `state.save_steps` / `state.eval_steps`, and
    `Trainer._init_training_state` replaces the whole TrainerState with the checkpoint's on resume. Without the
    `CadenceFromArgs` callback the run silently keeps the cadence it started with: on 2026-09-25 run F was moved to
    20 / 122, reported `save_steps: 20` in `training_args.bin`, and still saved at step 90 and evaluated every 50.
    """
    import train_vlm_lora as tv
    from transformers import TrainerState, TrainingArguments

    args = TrainingArguments(output_dir=str(tmp_path), save_strategy="steps", eval_strategy="steps",
                             save_steps=20, eval_steps=122, logging_steps=1, report_to=[])
    state = TrainerState()                                  # as restored from a checkpoint written by the older run
    state.max_steps, state.global_step = 488, 90
    state.save_steps, state.eval_steps, state.logging_steps = 10, 50, 1

    cadence = tv.make_callbacks(tmp_path, [], tmp_path / "backup")[0]
    assert type(cadence).__name__ == "CadenceFromArgs", "the cadence fix must run before the other callbacks"
    cadence.on_train_begin(args, state, None)
    assert (state.save_steps, state.eval_steps) == (20, 122)
    assert 110 % state.save_steps != 0 and 120 % state.save_steps == 0    # the off-cadence save at 90/110 is gone


def test_cadence_knobs_are_not_in_the_fingerprinted_settings(cfg):
    """A resume must accept a changed checkpoint/eval cadence, so neither knob may reach the plan fingerprint.

    Raising `checkpoint_steps` or `eval_steps` mid-run is safe only because they do not change which rows a step
    trains on. Both were raised during run F (2026-09-25) while the 30B was training, and the resume had to match
    `runs/herald-f-lora/plan_fingerprint.json` exactly. This reads the real settings dict out of the source with the
    AST rather than restating it, so adding a cadence key to it later fails here instead of at the next resume.
    """
    import ast

    src = ast.parse((ROOT / "scripts" / "train_vlm_lora.py").read_text())
    dicts = [n.args[2] for n in ast.walk(src)
             if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "plan_fingerprint"]
    assert len(dicts) == 1, "expected exactly one plan_fingerprint call in train_vlm_lora.py"
    keys = {k.value for k in dicts[0].keys}
    assert keys == {"base", "steps", "accum", "lora", "optim"}
    for knob in ("checkpoint_steps", "eval_steps", "reference_tokens_per_s", "keep_checkpoints"):
        assert knob in cfg and knob not in keys                  # a real config key, deliberately not fingerprinted

    # ...and the fingerprint really is blind to them, given that key set.
    import ckpt_safety

    settings = {"base": "m", "steps": 1, "accum": cfg["batching"]["accum"],
                "lora": cfg["lora"], "optim": cfg["optim"]}
    rows, batches = [("text", "a"), ("image", "b")], [[0, 1]]
    assert ckpt_safety.plan_fingerprint(rows, batches, settings) == \
        ckpt_safety.plan_fingerprint(rows, batches, dict(settings))


def test_dev_passes_land_on_both_epoch_ends(cfg):
    """`eval_steps` must divide the run so that each epoch's last step is measured (MODEL_PLAN §0l).

    Under the original 50 the final step 488 got no dev pass at all, because 488 is not a multiple of 50: the
    epoch-2 adapter was chosen against a dev loss from step 450.
    """
    run_cfg = ROOT / "runs" / "herald-f-lora" / "run_config.json"
    if not run_cfg.exists():
        pytest.skip("no run F plan on this box; the step count comes from the planned mix")
    plan = json.loads(run_cfg.read_text())["plan"]
    for end in plan["epoch_end_steps"] + [plan["optimizer_steps"]]:
        assert end % cfg["eval_steps"] == 0, f"no dev pass at step {end}"


def test_copy_dir_atomic_replaces_whole(tmp_path):
    import ckpt_safety

    src = tmp_path / "epoch-1"
    src.mkdir()
    (src / "adapter_model.safetensors").write_bytes(b"new")
    dst = tmp_path / "backup" / "epoch-1"
    dst.mkdir(parents=True)
    (dst / "stale.txt").write_text("old")
    ckpt_safety.copy_dir_atomic(src, dst)
    assert sorted(p.name for p in dst.iterdir()) == ["adapter_model.safetensors"]
    assert not list(dst.parent.glob(".*"))                    # no temp dirs left


def test_supervisor_retries_with_backoff_then_gives_up(tmp_path):
    import train_supervised as ts

    sv = {"backoff_s": 60, "backoff_cap_s": 900, "max_failures": 3, "tempfail_wait_s": 5}
    codes, sleeps = iter([75, 1, 137, 0]), []
    assert ts.supervise(["x"], sv, tmp_path / "log", lambda c, l: next(codes), sleeps.append) == 0
    assert sleeps == [5, 60, 120]                              # refused start: short wait, not counted
    sleeps.clear()
    assert ts.supervise(["x"], sv, tmp_path / "log", lambda c, l: 1, sleeps.append) == 1   # cap reached
    assert sleeps == [60, 120]
    assert ts.supervise(["x"], sv, tmp_path / "log", lambda c, l: 3, sleeps.append) == 3   # plan changed: no retry
    log = [json.loads(x) for x in (tmp_path / "log").read_text().splitlines()]
    assert {"start", "exit", "backoff", "gave_up", "permanent_failure"} <= {r["event"] for r in log}
    assert [ts.backoff(i, 60, 900) for i in range(1, 8)] == [0, 60, 120, 240, 480, 900, 900]


def test_supervisor_command_resumes_through_run_job(cfg):
    import train_supervised as ts

    sv = cfg["supervisor"]
    cmd = ts.command(sv, ["--max-steps", "20"], {"--priority"})
    i = cmd.index("--")
    assert cmd[1].endswith("run_job.py") and "--gpu" in cmd[:i] and cmd[cmd.index("--priority") + 1] == "critical"
    assert cmd[i + 2].endswith("train_vlm_lora.py") and cmd[i + 3] == "--resume" and cmd[-2:] == ["--max-steps", "20"]
    assert "--priority" not in ts.command(sv, [], set())       # older run_job.py without the flag


def test_checkpoint_cadence_bounds_lost_work(cfg):
    """At the reference speed a checkpoint interval costs at most ~12 minutes of work (MODEL_PLAN §0l)."""
    step_tokens = cfg["batching"]["max_tokens"] * cfg["batching"]["accum"]        # upper bound per optimizer step
    assert cfg["checkpoint_steps"] * step_tokens / cfg["reference_tokens_per_s"] <= 16 * 60
    assert cfg["keep_checkpoints"] >= 3 and cfg["adapter_backup_dir"]


def test_epoch_adapter_records_its_own_dev_losses(tmp_path):
    """`herald_epoch.json` must carry the dev losses measured on the adapter's own step.

    transformers evaluates after `on_step_end` (trainer.py:1882 `on_step_end`, then :1883
    `_maybe_log_save_evaluate`, which evaluates at :2196 and fires `on_evaluate` at :2781), so the old
    `on_step_end`-only write recorded the previous dev pass: `runs/herald-f-lora/epoch-1/herald_epoch.json` says
    `"step": 244` and carries eval rows tagged 122, epoch-2 says 488 with rows from 366. TRAINING_PLAN §4.3 picks the
    better epoch out of this file, so the choice was made on stale numbers.
    """
    import ckpt_safety
    import train_vlm_lora as tv
    from transformers import TrainerControl, TrainerState

    class FakeModel:
        def save_pretrained(self, d):
            Path(d).mkdir(parents=True, exist_ok=True)
            (Path(d) / "adapter_model.safetensors").write_bytes(b"weights")

    out, backup = tmp_path / "run", tmp_path / "backup"
    out.mkdir()
    epochs = tv.make_callbacks(out, [244, 488], backup, dev_passes=3)[-1]
    assert type(epochs).__name__ == "EpochAdapters"
    state, control = TrainerState(), TrainerControl()
    state.log_history = [{"step": 122, "eval_text_loss": 0.119}, {"step": 122, "eval_image_loss": 0.268},
                         {"step": 122, "eval_replay_loss": 0.096}]
    state.global_step = 244
    epochs.on_step_end(None, state, control, model=FakeModel())
    assert not (out / "epoch-1").exists()                     # nothing final before this step's dev passes land
    for i, key in enumerate(("eval_text_loss", "eval_image_loss", "eval_replay_loss")):
        state.log_history.append({"step": 244, key: 0.1 + i})
        epochs.on_evaluate(None, state, control, metrics={key: 0.1 + i})
        assert (out / "epoch-1").exists() == (i == 2)          # written once, after the last dev set
    rec = json.loads((out / "epoch-1" / "herald_epoch.json").read_text())
    assert rec == {"epoch": 1, "step": 244,
                   "eval": [{"step": 244, "eval_text_loss": 0.1}, {"step": 244, "eval_image_loss": 1.1},
                            {"step": 244, "eval_replay_loss": 2.1}]}
    assert ckpt_safety.is_complete(out / "epoch-1")            # still marked complete, and copied to the backup
    assert json.loads((backup / "epoch-1" / "herald_epoch.json").read_text())["step"] == 244
    assert not list(out.glob(".epoch-*"))                      # temp dir renamed, nothing left behind


def test_epoch_adapter_is_kept_even_without_a_dev_pass(tmp_path):
    """A dev pass that never arrives (a cadence that misses the epoch end) must not cost us the adapter."""
    import train_vlm_lora as tv
    from transformers import TrainerControl, TrainerState

    class FakeModel:
        def save_pretrained(self, d):
            Path(d).mkdir(parents=True, exist_ok=True)
            (Path(d) / "adapter_model.safetensors").write_bytes(b"weights")

    out, backup = tmp_path / "run", tmp_path / "backup"
    out.mkdir()
    epochs = tv.make_callbacks(out, [10, 20], backup, dev_passes=3)[-1]
    state, control = TrainerState(), TrainerControl()
    state.log_history, state.global_step = [], 10
    epochs.on_step_end(None, state, control, model=FakeModel())
    state.global_step = 11
    epochs.on_step_end(None, state, control, model=FakeModel())          # training moved on: finish it anyway
    assert json.loads((out / "epoch-1" / "herald_epoch.json").read_text()) == {"epoch": 1, "step": 10, "eval": []}
    state.global_step = 20
    epochs.on_step_end(None, state, control, model=FakeModel())
    epochs.on_train_end(None, state, control)                            # last epoch: the run ends first
    assert json.loads((out / "epoch-2" / "herald_epoch.json").read_text())["step"] == 20


def test_memory_sampler_is_closed_once_on_both_paths(tmp_path):
    """The sampler thread and its `"final": true` line were left dangling: `close()` was never called.

    It matters on the exception path most of all: a run that ends on a torch OOM left a mem.jsonl with no final
    marker, which reads exactly like the abrupt stop this sampler exists to record. Wiring it was deferred while
    run F was training, because the supervisor relaunches the trainer and would have re-read a half-edited file.
    """
    import ast

    import lora_common as lc

    class Spy(lc.MemorySampler):
        def __init__(self):
            super().__init__(tmp_path / "mem.jsonl")
            self.closes = 0

        def start(self):                       # no thread, no torch: this test only counts the teardown
            return self

        def close(self):
            self.closes += 1

    s = Spy()
    with s:
        pass
    assert s.closes == 1
    s = Spy()
    with pytest.raises(RuntimeError):
        with s:
            raise RuntimeError("torch.OutOfMemoryError stands in here")
    assert s.closes == 1

    # ...and the trainer really does hold it that way: every MemorySampler in main() is a `with` item, and the
    # training call sits inside that block.
    main = next(n for n in ast.walk(ast.parse((ROOT / "scripts" / "train_vlm_lora.py").read_text()))
                if isinstance(n, ast.FunctionDef) and n.name == "main")
    withs = [w for w in ast.walk(main) if isinstance(w, ast.With)
             for item in w.items if isinstance(item.context_expr, ast.Call)
             and getattr(item.context_expr.func, "id", None) == "MemorySampler"]
    built = [n for n in ast.walk(main) if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "MemorySampler"]
    assert len(built) == 1 and len(withs) == 1, "MemorySampler must be constructed once, as a context manager"
    trains = [n for n in ast.walk(withs[0]) if isinstance(n, ast.Call)
              and getattr(n.func, "attr", None) == "train" and getattr(n.func.value, "id", None) == "trainer"]
    assert len(trains) == 1, "trainer.train must run inside the sampler's block"
