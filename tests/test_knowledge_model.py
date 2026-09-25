"""The split stack (TRAINING_PLAN §7a): `HERALD_KNOWLEDGE_MODEL` moves protocol reranking, figure transcription and
translation onto a different served label from photo reading, and moves nothing else.

It exists for one outcome: a fine-tune that wins speech and photos but loses the base model's kept abilities. Unset,
which is the default and today's stack, the knowledge client is the *same object* as the photo client, so nothing about
the single-model path changes.

Targeted and offline: no model is served, no weights are loaded, and `/api/telemetry` is exercised through
`Telemetry.snapshot` rather than over HTTP so nothing reaches for the metrics port.
"""
from fakes import FakeModel, FakeSTT, FakeVision, make_client
from fakes import test_settings as settings_for      # aliased: pytest would collect the name `test_settings`

from herald.api.context import build_context
from herald.telemetry import Telemetry


def _ctx(**settings):
    """A context over fakes with the knowledge service built (no embedder, so no model is loaded)."""
    return build_context(settings_for(knowledge=True, **settings), text_model=FakeModel(name="extract"),
                         vision_model=FakeModel(name="photos"), stt=FakeSTT(), vision=FakeVision())


def test_unset_shares_one_client_with_photo_reading():
    ctx = _ctx()
    assert ctx.settings.knowledge_model is None
    assert ctx.knowledge_model is ctx.vision_model               # the same object, not merely the same label
    assert ctx.knowledge.reranker.model is ctx.vision_model      # reranking
    assert ctx.knowledge.vision is ctx.vision_model              # figure transcription


def test_set_moves_rerank_and_figures_and_nothing_else():
    ctx = _ctx(knowledge_model="qwen3vl-fp8")
    assert ctx.knowledge_model is not ctx.vision_model
    assert ctx.knowledge_model.model_name() == "qwen3vl-fp8"     # pinned label; LocalLLMClient does no I/O to answer
    assert ctx.knowledge.reranker.model is ctx.knowledge_model   # reranking moved
    assert ctx.knowledge.vision is ctx.knowledge_model           # figure transcription moved
    assert ctx.vision_model.model_name() == "photos"             # photo reading did not
    assert ctx.text_model.model_name() == "extract"              # extraction did not


def test_one_url_serves_both_labels():
    """ZRT's proxy routes by label on a single endpoint (/opt/hp/zrt/proxy.json: one host/port, a `services` list),
    so the split needs no second URL setting: both clients point at `llm_url`."""
    ctx = _ctx(knowledge_model="qwen3vl-fp8")
    assert ctx.knowledge_model.base_url == ctx.settings.llm_url.rstrip("/")


def test_an_injected_client_wins():
    """Tests, and Shivani's interpreter (S3), can hand in their own client instead of a label."""
    own = FakeModel(name="knowing")
    ctx = build_context(settings_for(knowledge=True), text_model=FakeModel(name="extract"),
                        vision_model=FakeModel(name="photos"), knowledge_model=own,
                        stt=FakeSTT(), vision=FakeVision())
    assert ctx.knowledge_model is own
    assert ctx.knowledge.reranker.model is own and ctx.knowledge.vision is own


def test_stack_response_is_unchanged_without_the_split():
    """The public API is a contract (AGENTS.md): the single-model response must not grow a key."""
    c, _ = make_client()
    assert "jobs" not in c.get("/api/stack").json()


def test_stack_names_each_job_with_the_split():
    c, _ = make_client(model=FakeModel(name="extract"), vision_model=FakeModel(name="photos"),
                       knowledge_model="qwen3vl-fp8")
    assert c.get("/api/stack").json()["jobs"] == {
        "extraction": "extract", "photos": "photos", "knowledge": "qwen3vl-fp8"}


def test_telemetry_reports_jobs_only_when_asked():
    tel = Telemetry("http://127.0.0.1:8080/metrics", {})
    assert "jobs" not in tel.snapshot(None)                     # model=None, so nothing touches the metrics port
    jobs = {"extraction": "herald-f", "photos": "herald-f", "knowledge": "qwen3vl-fp8"}
    assert tel.snapshot(None, jobs)["jobs"] == jobs


def test_env_var_reads_the_label():
    from herald.config.settings import Settings

    assert Settings.from_env({}).knowledge_model is None
    assert Settings.from_env({"HERALD_KNOWLEDGE_MODEL": "qwen3vl-fp8"}).knowledge_model == "qwen3vl-fp8"
    assert Settings.from_env({"HERALD_KNOWLEDGE_MODEL": ""}).knowledge_model is None      # empty means unset
