"""Unit tests for GET /chat/stream. workflow.astream is faked, so no Neo4j or LLM needed -- these
mimic the exact event shapes measured live against the real graph (see the plan)."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

import app.api as api_module
import app.store as store_module
from app.api import app

client = TestClient(app)


class FakeChunk:
    """Stand-in for langchain_core's AIMessageChunk: .text is what the endpoint reads."""

    def __init__(self, text: str):
        self.text = text


def fake_document(doc_id: str) -> dict:
    return {"id": doc_id, "name": "doc.pdf", "status": "done", "mode": "long", "progress": 1.0,
            "created_at": 0, "updated_at": 0, "tokens": 10, "chunks": 1, "error": None,
            "step_done": None, "step_total": None}


def parse_sse(text: str) -> list[tuple[str, object]]:
    events = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        lines = block.strip().split("\n")
        event = next(l.removeprefix("event: ") for l in lines if l.startswith("event: "))
        data = next(l.removeprefix("data: ") for l in lines if l.startswith("data: "))
        events.append((event, json.loads(data)))
    return events


@pytest.fixture
def stubbed(monkeypatch):
    monkeypatch.setattr(store_module, "get_file", fake_document)
    saved = {}
    monkeypatch.setattr(store_module, "save_turn", lambda file_id, **kw: saved.update(kw) or saved)
    return saved


def test_citations_precede_tokens_leaked_nodes_filtered_newline_survives(stubbed, monkeypatch):
    async def fake_stream(state, stream_mode):
        yield ("updates", {"vector_retrieve": {"retrieved": []}})
        yield ("updates", {"fuse": {"contexts": [
            {"id": "f:0", "text": "hello", "pages": [1], "headings": [], "source": "vector"},
        ]}})
        # a real leak observed live: kg_retrieve's structured-output JSON streams as "messages" too
        yield ("messages", (FakeChunk('{"names": []}'), {"langgraph_node": "kg_retrieve"}))
        yield ("messages", (FakeChunk(""), {"langgraph_node": "generate"}))  # role-only chunk
        yield ("messages", (FakeChunk("Hello\nworld"), {"langgraph_node": "generate"}))
        yield ("updates", {"generate": {"answer": "Hello\nworld", "citations": []}})

    monkeypatch.setattr(api_module.workflow, "astream", fake_stream)

    with client.stream("GET", "/chat/stream", params={"doc_id": "d1", "question": "hi?"}) as r:
        assert r.status_code == 200
        events = parse_sse(r.read().decode())

    kinds = [e for e, _ in events]
    assert kinds.index("citations") < kinds.index("token"), "citations must precede the first token"
    assert kinds.count("token") == 1, "the kg_retrieve leak and the empty chunk must both be filtered"
    assert [d for e, d in events if e == "token"] == ["Hello\nworld"], "newline in a token must survive JSON round-trip"
    assert [d for e, d in events if e == "status"] == [{"node": "vector_retrieve"}]
    assert kinds[-1] == "done"

    assert stubbed["answer"] == "Hello\nworld"
    assert stubbed["complete"] is True


def test_disconnect_mid_stream_persists_partial_answer_as_incomplete(stubbed, monkeypatch):
    # An endless fake stream: the point is that stream_answer is closed from the *outside*
    # (aclose(), what uvicorn's task cancellation does to a suspended async generator on a real
    # client disconnect -- confirmed empirically that the equivalent sync-generator design left a
    # killed connection's answer unsaved even after 17+ seconds, which is why this is now async).
    async def fake_stream(state, stream_mode):
        yield ("updates", {"fuse": {"contexts": []}})
        yield ("messages", (FakeChunk("partial"), {"langgraph_node": "generate"}))
        while True:
            yield ("messages", (FakeChunk("more"), {"langgraph_node": "generate"}))

    monkeypatch.setattr(api_module.workflow, "astream", fake_stream)

    async def run():
        gen = api_module.stream_answer("d1", "hi?", "long")
        await anext(gen)  # citations
        await anext(gen)  # token "partial"
        await gen.aclose()

    asyncio.run(run())

    assert stubbed["answer"] == "partial"
    assert stubbed["complete"] is False


def test_document_not_ready_returns_409_before_streaming_starts(monkeypatch):
    monkeypatch.setattr(store_module, "get_file", lambda doc_id: {**fake_document(doc_id), "status": "converting"})
    r = client.get("/chat/stream", params={"doc_id": "d1", "question": "hi?"})
    assert r.status_code == 409


def test_unknown_document_returns_404_before_streaming_starts(monkeypatch):
    monkeypatch.setattr(store_module, "get_file", lambda doc_id: None)
    r = client.get("/chat/stream", params={"doc_id": "nope", "question": "hi?"})
    assert r.status_code == 404
