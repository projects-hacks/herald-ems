"""The local model client: 'available' means the server is up AND serving the configured label."""
import httpx
import pytest

from herald.models.llm_client import LocalLLMClient


def _serve(monkeypatch, labels=None, down=False):
    calls = []

    def get(url, timeout):
        calls.append(url)
        if down:
            raise httpx.ConnectError("refused")
        return httpx.Response(200, json={"data": [{"id": x} for x in labels]}, request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx, "get", get)
    return calls


def test_a_configured_label_the_server_does_not_serve_is_unavailable(monkeypatch):
    _serve(monkeypatch, ["omni", "ems-c-fp8"])
    assert LocalLLMClient("http://127.0.0.1:8080/v1", "ems-c-fp8").available()
    missing = LocalLLMClient("http://127.0.0.1:8080/v1", "not-served")
    assert not missing.available() and missing.model_name() == "not-served"   # the screen can name what's missing


def test_server_down_is_unavailable(monkeypatch):
    _serve(monkeypatch, down=True)
    assert not LocalLLMClient("http://127.0.0.1:8080/v1", "ems-c-fp8").available()
    assert LocalLLMClient("http://127.0.0.1:8080/v1").model_name() is None


def test_availability_is_cached_briefly_not_checked_per_utterance(monkeypatch):
    calls = _serve(monkeypatch, ["ems-c-fp8"])
    c = LocalLLMClient("http://127.0.0.1:8080/v1", "ems-c-fp8", availability_ttl=60)
    assert all(c.available() for _ in range(5)) and len(calls) == 1
    c.availability_ttl = -1
    c.available()
    assert len(calls) == 2


def test_only_this_box():
    with pytest.raises(RuntimeError):
        LocalLLMClient("https://api.example.com/v1", "x")


def test_local_weights_resolve_to_a_folder_and_never_download(tmp_path):
    from herald.models.weights import local_weights
    assert local_weights(str(tmp_path)) == str(tmp_path)
    with pytest.raises(RuntimeError, match="not on this box"):
        local_weights("nobody/not-a-real-model-xyz")
