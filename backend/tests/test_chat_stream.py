"""GET /chat/stream with workflow.astream faked to the event shapes the real graph emits."""
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
    monkeypatch.setattr(store_module, "recent_turns", lambda file_id, n: [])
    saved = {}
    monkeypatch.setattr(store_module, "save_turn", lambda file_id, **kw: saved.update(kw) or saved)
    return saved


def test_chat_history_reads_only_the_turns_the_graph_uses(monkeypatch):
    seen = []

    class Graph:
        def query(self, statement, params):
            seen.append((statement, params))
            return [{"question": "q1", "answer": "a1"}]

    monkeypatch.setattr(store_module, "graph", lambda: Graph())
    assert api_module.chat_history("d1") == [{"question": "q1", "answer": "a1"}]
    [(statement, params)] = seen
    assert "WHERE t.complete" in statement, "interrupted turns are not history"
    assert params["n"] == api_module.MAX_HISTORY_TURNS


def test_stream_answer_passes_history_through_to_the_graph(stubbed, monkeypatch):
    monkeypatch.setattr(store_module, "recent_turns", lambda file_id, n: [{"question": "earlier q", "answer": "earlier a"}])
    seen_state = {}

    async def fake_stream(state, stream_mode):
        seen_state.update(state)
        yield ("updates", {"fuse": {"contexts": []}})

    monkeypatch.setattr(api_module.workflow, "astream", fake_stream)

    with client.stream("GET", "/chat/stream", params={"doc_id": "d1", "question": "hi?"}) as r:
        r.read()

    assert seen_state["history"] == [{"question": "earlier q", "answer": "earlier a"}]


def test_stream_answer_passes_the_document_language_to_the_graph(stubbed, monkeypatch):
    monkeypatch.setattr(store_module, "get_file", lambda doc_id: {**fake_document(doc_id), "language": "English"})
    seen_state = {}

    async def fake_stream(state, stream_mode):
        seen_state.update(state)
        yield ("updates", {"fuse": {"contexts": []}})

    monkeypatch.setattr(api_module.workflow, "astream", fake_stream)

    with client.stream("GET", "/chat/stream", params={"doc_id": "d1", "question": "Berapa nilainya?"}) as r:
        r.read()

    assert seen_state["language"] == "English"


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
    # Endless stream closed from outside with aclose(), as uvicorn does on a client disconnect
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


@pytest.mark.parametrize("fails", [False, True])
def test_the_turn_is_saved_before_the_final_event_goes_out(stubbed, monkeypatch, fails):
    # The client refetches history on "done"/"failed": a Turn written after the event could be missed
    async def fake_stream(state, stream_mode):
        yield ("messages", (FakeChunk("answer"), {"langgraph_node": "generate"}))
        if fails:
            raise RuntimeError("model down")

    monkeypatch.setattr(api_module.workflow, "astream", fake_stream)

    async def run():
        events = []
        async for frame in api_module.stream_answer("d1", "hi?", "long"):
            events.append((parse_sse(frame)[0][0], "answer" in stubbed))
        return events

    final_event, saved_by_then = asyncio.run(run())[-1]
    assert final_event == ("failed" if fails else "done")
    assert saved_by_then
    assert stubbed["complete"] is (not fails)


def test_document_not_ready_returns_409_before_streaming_starts(monkeypatch):
    monkeypatch.setattr(store_module, "get_file", lambda doc_id: {**fake_document(doc_id), "status": "converting"})
    r = client.get("/chat/stream", params={"doc_id": "d1", "question": "hi?"})
    assert r.status_code == 409


def test_unknown_document_returns_404_before_streaming_starts(monkeypatch):
    monkeypatch.setattr(store_module, "get_file", lambda doc_id: None)
    r = client.get("/chat/stream", params={"doc_id": "nope", "question": "hi?"})
    assert r.status_code == 404


def test_citations_event_carries_regions_when_present_and_empty_when_not(stubbed, monkeypatch):
    region = {"page": 1, "l": 0, "t": 0, "r": 10, "b": 10, "page_width": 600, "page_height": 800}

    async def fake_stream(state, stream_mode):
        yield ("updates", {"fuse": {"contexts": [
            {"id": "f:0", "text": "has a highlight", "pages": [1], "headings": [], "regions": [region], "source": "vector"},
            {"id": "f:1", "text": "no highlight", "pages": [2], "headings": [], "regions": [], "source": "vector"},
        ]}})

    monkeypatch.setattr(api_module.workflow, "astream", fake_stream)

    with client.stream("GET", "/chat/stream", params={"doc_id": "d1", "question": "hi?"}) as r:
        events = parse_sse(r.read().decode())

    [(_, citations)] = [(e, d) for e, d in events if e == "citations"]
    assert [c["regions"] for c in citations] == [[region], []]
