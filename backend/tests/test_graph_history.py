"""Unit tests for graph.py's conversational-history plumbing: recent_history's cap, and
contextualize's skip-when-no-history short circuit (no LLM needed) plus its rewrite path (LLM
stubbed). Retrieval and generate's own correctness are exercised live by test_smoke.py; these
test the history-specific logic in isolation, no Neo4j or provider required."""
import app.graph as graph_module


def test_strip_citations_removes_bracketed_numbers_only():
    text = "3. Structured content yields big gains [3]. Also see [12] and item 4."
    assert graph_module.strip_citations(text) == "3. Structured content yields big gains . Also see  and item 4."


def test_recent_history_caps_to_max_turns():
    history = [{"question": f"q{i}", "answer": f"a{i}"} for i in range(10)]
    result = graph_module.recent_history({"history": history})
    assert len(result) == graph_module.MAX_HISTORY_TURNS
    assert result[0]["question"] == f"q{10 - graph_module.MAX_HISTORY_TURNS}"


def test_contextualize_skips_llm_call_when_no_history():
    # No history: must resolve without touching the LLM at all -- if this reached llm() it would
    # try to build a real provider client and fail in this test's unconfigured environment.
    result = graph_module.contextualize({"question": "what is this document about?", "history": []})
    assert result == {"search_query": "what is this document about?"}


class _FakeLLM:
    def __init__(self, content: str):
        self._content = content

    def invoke(self, messages):
        return type("Message", (), {"content": self._content})()


def test_contextualize_rewrites_follow_up_using_history(monkeypatch):
    monkeypatch.setattr(graph_module, "llm", lambda model=None: _FakeLLM("What does the second finding say?"))

    state = {
        "question": "what about the second one?",
        "history": [{"question": "what are the key findings?", "answer": "1. A. 2. B."}],
    }
    assert graph_module.contextualize(state) == {"search_query": "What does the second finding say?"}


def test_contextualize_falls_back_to_original_question_if_llm_returns_empty(monkeypatch):
    monkeypatch.setattr(graph_module, "llm", lambda model=None: _FakeLLM("   "))

    state = {"question": "and then?", "history": [{"question": "q", "answer": "a"}]}
    assert graph_module.contextualize(state) == {"search_query": "and then?"}


def test_a_long_document_also_searches_vectors_and_fuses_once(monkeypatch):
    chunk = lambda cid: {"id": cid, "text": cid, "pages": [1], "headings": [], "regions": None}
    monkeypatch.setattr(graph_module.vector, "search", lambda doc_id, query: [chunk("f:1")])
    monkeypatch.setattr(graph_module.tree_search, "search", lambda doc_id, query, model: [chunk("f:2")])
    monkeypatch.setattr(graph_module.kg, "search", lambda doc_id, query, model: ([], [chunk("f:1")]))
    monkeypatch.setattr(graph_module, "tokenizer", lambda: type("T", (), {"count_tokens": staticmethod(len)})())
    monkeypatch.setattr(graph_module, "llm", lambda model=None: _FakeLLM("answer"))

    updates = list(graph_module.workflow.stream(
        {"question": "q", "doc_id": "f", "mode": "long", "history": []}, stream_mode="updates",
    ))

    fused = [u["fuse"] for u in updates if "fuse" in u]
    assert len(fused) == 1, "fuse waits for all three retrievers, then runs once"
    assert {c["source"] for c in fused[0]["contexts"]} == {"tree", "vector"}, "vector hits reach the answer"
