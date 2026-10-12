"""Model endpoints set from Settings. Neo4j and the model servers are faked."""
import pytest
from fastapi.testclient import TestClient

import app.api as api_module
from app import auth, model_settings, models
from app.api import app
from app.config import settings

client = TestClient(app)

FORM = {
    "llm_provider": "openai", "llm_base_url": "https://api.example.com/v1/", "llm_api_key": "sk-new-key-1234",
    "llm_model": "big-model", "llm_model_choices": "small-model", "llm_reasoning_effort": "",
    "table_llm_base_url": "", "table_llm_api_key": None, "table_llm_model": "",
}


@pytest.fixture
def stored(monkeypatch):
    """The saved chat models' Meta node as a dict; settings are put back after each test."""
    nodes: dict[str, dict] = {"models": {}, "embedding_endpoint": {}}
    node = nodes["models"]

    class Graph:
        def query(self, statement: str, params: dict | None = None) -> list:
            if statement == model_settings.READ:
                return [{"m": dict(nodes[params["key"]]) or None}]
            if statement == model_settings.WRITE:
                nodes[params["key"]].clear()
                nodes[params["key"]].update(params["props"])
            elif statement == model_settings.DELETE:
                nodes[params["key"]].clear()
            return []

    monkeypatch.setattr(model_settings, "graph", lambda: Graph())
    monkeypatch.setitem(model_settings.ENV, "llm_api_key", "sk-env-key-9999")
    monkeypatch.setitem(model_settings.ENV, "llm_model", "env-model")
    monkeypatch.setitem(model_settings.ENV, "table_llm_api_key", "")
    model_settings.apply({})
    yield node
    monkeypatch.undo()
    model_settings.apply({})


def test_saving_applies_at_once_and_a_reset_goes_back_to_env(stored):
    assert client.get("/settings/models").json()["saved"] is False

    response = client.put("/settings/models", json=FORM)
    assert response.status_code == 200, response.text
    assert settings.llm_model == "big-model"
    assert settings.llm_base_url == "https://api.example.com/v1", "trailing slash dropped"
    assert settings.llm_api_key == "sk-new-key-1234"
    assert settings.llm_reasoning_effort is None
    assert settings.available_llm_models() == ["big-model", "small-model"]
    assert stored["llm_model"] == "big-model"
    assert response.json()["saved"] is True

    assert client.delete("/settings/models").json()["saved"] is False
    assert settings.llm_model == "env-model"
    assert settings.llm_api_key == "sk-env-key-9999"


def test_keys_go_out_masked_and_a_masked_or_missing_key_keeps_the_stored_one(stored):
    client.put("/settings/models", json=FORM)
    view = client.get("/settings/models").json()
    assert view["llm_api_key"] == "••••1234"
    assert "sk-new" not in str(view)

    for echoed in (None, view["llm_api_key"]):
        client.put("/settings/models", json={**FORM, "llm_api_key": echoed, "llm_model": "other"})
        assert settings.llm_api_key == "sk-new-key-1234"
    assert settings.llm_model == "other"


@pytest.mark.parametrize("change", [
    {"llm_base_url": "api.example.com"},
    {"llm_model": " "},
    {"llm_provider": "ollama", "llm_base_url": "ftp://x"},
    {"table_llm_model": "t", "table_llm_base_url": "https://t.example.com"},
])
def test_a_broken_form_is_refused_and_changes_nothing(stored, change):
    response = client.put("/settings/models", json={**FORM, **change})
    assert response.status_code == 400, response.text
    assert stored == {}
    assert settings.llm_model == "env-model"


def test_an_openai_server_needs_a_key(stored, monkeypatch):
    monkeypatch.setitem(model_settings.ENV, "llm_api_key", "")
    model_settings.apply({})
    assert client.put("/settings/models", json={**FORM, "llm_api_key": None}).status_code == 400
    assert client.put("/settings/models", json={**FORM, "llm_provider": "ollama", "llm_api_key": None}).status_code == 200


def test_only_admins_see_or_change_model_settings(stored):
    app.dependency_overrides[auth.require_user] = lambda: {"id": "u1", "username": "budi", "role": "user"}
    assert client.get("/settings/models").status_code == 403
    assert client.put("/settings/models", json=FORM).status_code == 403
    assert client.post("/settings/models/test", json={"slot": "chat", "base_url": "http://x", "model": "m"}).status_code == 403


def test_the_connection_test_uses_the_form_and_falls_back_to_the_stored_key(stored, monkeypatch):
    calls = []

    class Reply:
        text = " OK "

    class Client:
        def __init__(self, fail):
            self.fail = fail

        def invoke(self, prompt):
            if self.fail:
                raise ConnectionError("connection refused")
            return Reply()

    def chat_model(provider, base_url, api_key, model, **options):
        calls.append((provider, base_url, api_key, model))
        return Client(fail=model == "down")

    monkeypatch.setattr(api_module, "chat_model", chat_model)
    ok = client.post("/settings/models/test", json={
        "slot": "chat", "provider": "ollama", "base_url": "http://localhost:11434/", "model": "qwen3:14b",
    }).json()
    assert ok["ok"] is True
    assert ok["reply"] == "OK"
    assert calls[-1] == ("ollama", "http://localhost:11434", "sk-env-key-9999", "qwen3:14b")

    client.post("/settings/models/test", json={"slot": "table", "provider": "ollama", "base_url": "https://t", "model": "t", "api_key": "sk-typed"})
    assert calls[-1] == ("openai", "https://t", "sk-typed", "t"), "the table model is always OpenAI-compatible"

    failed = client.post("/settings/models/test", json={"slot": "chat", "base_url": "http://x", "model": "down"}).json()
    assert failed["ok"] is False
    assert "connection refused" in failed["error"]


def test_a_document_whose_model_is_no_longer_offered_falls_back_to_the_default(stored, monkeypatch):
    built = []
    monkeypatch.setattr(models, "_llm", lambda model, temperature, max_tokens: built.append(model))
    models.llm("a-model-from-the-old-server")
    models.llm(None)
    assert built == ["env-model", "env-model"]
