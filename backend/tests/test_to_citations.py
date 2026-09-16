"""Unit tests for app.graph.to_citations. No Neo4j or LLM needed."""
from app.graph import to_citations


def test_numbers_contexts_from_one_and_keeps_all_fields():
    contexts = [
        {"id": "f:0", "text": "first chunk", "pages": [1, 2], "headings": ["Intro"], "source": "vector"},
        {"id": "f:1", "text": "second chunk", "pages": [3], "headings": [], "source": "tree"},
    ]
    citations = to_citations(contexts)
    assert citations == [
        {"n": 1, "chunk_id": "f:0", "pages": [1, 2], "headings": ["Intro"], "source": "vector", "text": "first chunk"},
        {"n": 2, "chunk_id": "f:1", "pages": [3], "headings": [], "source": "tree", "text": "second chunk"},
    ]


def test_kg_facts_synthetic_entry_has_no_headings_or_pages():
    contexts = [{"id": "kg:facts", "text": "(A) -[REL]-> (B)", "pages": [], "headings": [], "source": "kg_facts"}]
    [citation] = to_citations(contexts)
    assert citation == {
        "n": 1, "chunk_id": "kg:facts", "pages": [], "headings": [], "source": "kg_facts", "text": "(A) -[REL]-> (B)",
    }


def test_missing_headings_key_defaults_to_empty_list():
    # Older chunk rows or hand-built dicts may omit "headings" entirely
    contexts = [{"id": "f:0", "text": "x", "pages": [], "source": "vector"}]
    [citation] = to_citations(contexts)
    assert citation["headings"] == []


def test_empty_contexts_yields_empty_citations():
    assert to_citations([]) == []
