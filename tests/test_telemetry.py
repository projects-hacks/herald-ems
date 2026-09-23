from herald.telemetry import Telemetry, parse_prometheus

SAMPLE = """# HELP vllm:generation_tokens_total Number of generation tokens processed.
vllm:generation_tokens_total{engine="0",model_name="omni"} 35031.0
vllm:prompt_tokens_total{engine="0",model_name="omni"} 785046.0
vllm:request_success_total{engine="0",finished_reason="stop",model_name="omni"} 617.0
vllm:request_success_total{engine="0",finished_reason="length",model_name="omni"} 23.0
vllm:e2e_request_latency_seconds_sum{engine="0",model_name="omni"} NaN
"""


def test_parse_prometheus_sums_label_sets_and_skips_nan():
    m = parse_prometheus(SAMPLE)
    assert m["vllm:generation_tokens_total"] == 35031.0
    assert m["vllm:request_success_total"] == 640.0
    assert "vllm:e2e_request_latency_seconds_sum" not in m


def test_cost_math_uses_stated_assumptions():
    t = Telemetry()
    t.record_llm({"prompt_tokens": 1_000_000, "completion_tokens": 100_000})
    t.record_stt(600)                      # 10 minutes of audio
    t.energy_j = 3600 * 100                # 100 Wh
    s = t.snapshot(model=None)
    assert s["cost"]["cloud_breakdown"]["llm_usd"] == round(0.30 + 0.25, 5)
    assert s["cost"]["cloud_breakdown"]["stt_usd"] == round(10 * 0.006, 5)
    assert s["cost"]["local_usd"] == round(0.1 * 0.15, 5)
    assert s["cloud_ai_calls"] == 0
