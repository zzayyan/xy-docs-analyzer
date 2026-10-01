"""Unit tests for graph.py's question handling: recent_history's cap, contextualize's rewrite and
decomposition into search queries (LLM stubbed), and how the retrievers use several queries. Retrieval
and generate's own correctness are exercised live by test_smoke.py; these need no Neo4j or provider."""
import app.graph as graph_module


def test_strip_citations_removes_bracketed_numbers_only():
    text = "3. Structured content yields big gains [3]. Also see [12] and item 4."
    assert graph_module.strip_citations(text) == "3. Structured content yields big gains . Also see  and item 4."


def test_strip_citations_also_removes_grouped_markers():
    text = "Useful for fact-checking [4, 5], audits [6;7] and reviews [8-10]."
    assert graph_module.strip_citations(text) == "Useful for fact-checking , audits  and reviews ."


def test_recent_history_caps_to_max_turns():
    history = [{"question": f"q{i}", "answer": f"a{i}"} for i in range(10)]
    result = graph_module.recent_history({"history": history})
    assert len(result) == graph_module.MAX_HISTORY_TURNS
    assert result[0]["question"] == f"q{10 - graph_module.MAX_HISTORY_TURNS}"


class _FakeLLM:
    """Plain invoke answers with `content`; structured output answers with `queries`, or raises."""

    def __init__(self, content: str = "", queries: list[str] | Exception | None = None, seen: list | None = None):
        self._content = content
        self._queries = queries
        self._seen = seen if seen is not None else []

    def invoke(self, messages):
        return type("Message", (), {"content": self._content})()

    def with_structured_output(self, schema):
        fake = self

        class Structured:
            def invoke(self, messages):
                fake._seen.append(messages)
                if isinstance(fake._queries, Exception):
                    raise fake._queries
                return schema(queries=fake._queries if fake._queries is not None else [])

        return Structured()


def test_a_follow_up_is_rewritten_standalone_using_history(monkeypatch):
    seen = []
    monkeypatch.setattr(graph_module, "llm", lambda model=None: _FakeLLM(queries=["What does the second finding say?"], seen=seen))

    state = {
        "question": "what about the second one?",
        "history": [{"question": "what are the key findings?", "answer": "1. A [1]. 2. B [2]."}],
    }

    assert graph_module.contextualize(state) == {"search_queries": ["What does the second finding say?"]}
    prompt = seen[0][1][1]
    assert "Conversation so far" in prompt and "[1]" not in prompt, "history goes in, its citation markers do not"


def test_a_compound_first_question_is_split_into_deduplicated_queries(monkeypatch):
    seen = []
    split = ["nilai dan tenggat proyek A?", "nilai dan tenggat proyek B?", "nilai dan tenggat proyek A?"]
    monkeypatch.setattr(graph_module, "llm", lambda model=None: _FakeLLM(queries=split, seen=seen))

    result = graph_module.contextualize({"question": "Bandingkan nilai dan tenggat proyek A dan B", "history": []})

    assert result == {"search_queries": ["nilai dan tenggat proyek A?", "nilai dan tenggat proyek B?"]}
    assert "Conversation so far" not in seen[0][1][1], "a first question runs too, with no history block"


def test_a_split_past_the_cap_falls_back_to_the_question_rather_than_dropping_part_of_it(monkeypatch):
    # Measured on Qwen3.5-4B: an English comparison came back split by aspect as well as by thing, and
    # cutting it to three dropped one model's recall entirely
    by_aspect = ["precision of A?", "recall of A?", "precision of B?", "recall of B?"]
    monkeypatch.setattr(graph_module, "llm", lambda model=None: _FakeLLM(queries=by_aspect))

    question = "Compare precision and recall of A vs B"
    assert graph_module.contextualize({"question": question, "history": []}) == {"search_queries": [question]}


def test_no_usable_answer_falls_back_to_the_question_as_asked(monkeypatch):
    for answer in ([], ["   "], RuntimeError("model down")):
        monkeypatch.setattr(graph_module, "llm", lambda model=None, a=answer: _FakeLLM(queries=a))
        assert graph_module.contextualize({"question": "and then?", "history": []}) == {"search_queries": ["and then?"]}


def test_vector_search_runs_once_per_query_and_interleaves_their_best_hits(monkeypatch):
    hits = {"A?": ["a1", "a2", "a3"], "B?": ["b1"]}
    monkeypatch.setattr(graph_module.vector, "search", lambda doc_id, query: [{"id": i, "text": i} for i in hits[query]])

    retrieved = graph_module.vector_retrieve({"doc_id": "f", "question": "A and B?", "search_queries": ["A?", "B?"]})

    assert [r["id"] for r in retrieved["retrieved"]] == ["a1", "b1", "a2", "a3"]


def test_tree_search_gets_every_sub_question_in_one_call(monkeypatch):
    calls = []
    monkeypatch.setattr(graph_module.tree_search, "search", lambda doc_id, query, model: calls.append(query) or [])

    graph_module.tree_retrieve({"doc_id": "f", "question": "A and B?", "search_queries": ["A?", "B?"]})

    assert calls == ["A?\nB?"]


def test_a_long_document_also_searches_vectors_and_fuses_once(monkeypatch):
    chunk = lambda cid: {"id": cid, "text": cid, "pages": [1], "headings": [], "regions": None}
    monkeypatch.setattr(graph_module.vector, "search", lambda doc_id, query: [chunk("f:1")])
    monkeypatch.setattr(graph_module.tree_search, "search", lambda doc_id, query, model: [chunk("f:2")])
    monkeypatch.setattr(graph_module.kg, "search", lambda doc_id, query, model: ([], [chunk("f:1")]))
    monkeypatch.setattr(graph_module, "tokenizer", lambda: type("T", (), {"count_tokens": staticmethod(len)})())
    monkeypatch.setattr(graph_module, "llm", lambda model=None: _FakeLLM("answer", queries=["q"]))

    updates = list(graph_module.workflow.stream(
        {"question": "q", "doc_id": "f", "mode": "long", "history": []}, stream_mode="updates",
    ))

    fused = [u["fuse"] for u in updates if "fuse" in u]
    assert len(fused) == 1, "fuse waits for all three retrievers, then runs once"
    assert {c["source"] for c in fused[0]["contexts"]} == {"tree", "vector"}, "vector hits reach the answer"
