"""Table Extraction over every chunk of a document. The model is faked, so no LLM or Neo4j needed
(prior art: test_kg_parallel.py, which pins the same ordering and failure behaviour for graph extraction)."""
import threading
import time

import pytest

import app.table as table
from app.config import settings

COLUMNS = [
    {"name": "Kewajiban", "description": "The obligation as written"},
    {"name": "Tenggat", "description": "Its deadline"},
]


@pytest.fixture
def chunks():
    return [{"id": f"f:{i}", "text": f"text {i}", "pages": [i], "headings": [f"Bab {i}"]} for i in range(8)]


def fake_rows(values: list[list[str]]):
    return table.ChunkRows(rows=[table.ExtractedRow(values=v) for v in values])


def test_every_chunk_is_read_once_in_order_and_rows_cite_their_chunk(monkeypatch, chunks):
    threads: set[int] = set()

    def slow_extract(text, columns, model):
        threads.add(threading.get_ident())
        time.sleep(0.2)
        return fake_rows([[f"item {text[-1]}", "2027"]])

    monkeypatch.setattr(settings, "llm_concurrency", 4)
    monkeypatch.setattr(table, "extract_one", slow_extract)

    progress: list[tuple[int, int]] = []
    started = time.time()
    rows = table.run(chunks, COLUMNS, model=None, on_progress=lambda done, total: progress.append((done, total)))
    elapsed = time.time() - started

    assert len(threads) > 1, "chunks were not read in parallel"
    assert elapsed < 8 * 0.2, f"took {elapsed:.1f}s, no faster than sequential"
    assert [row["citations"][0]["chunk_id"] for row in rows] == [c["id"] for c in chunks], "chunk order must be kept"
    assert progress == [(i, 8) for i in range(1, 9)]
    assert rows[0] == {
        "values": {"Kewajiban": "item 0", "Tenggat": "2027"},
        "citations": [{"n": 1, "chunk_id": "f:0", "pages": [0], "headings": ["Bab 0"], "source": "table", "text": "text 0"}],
    }


def test_a_value_the_document_does_not_state_stays_empty(monkeypatch, chunks):
    # The model returns only the first column for one row, and a blank for the other
    monkeypatch.setattr(table, "extract_one", lambda text, columns, model: fake_rows([["item"], ["other", "  "]]))

    rows = table.run(chunks[:1], COLUMNS, model=None)

    assert [row["values"] for row in rows] == [
        {"Kewajiban": "item", "Tenggat": ""},
        {"Kewajiban": "other", "Tenggat": ""},
    ]


def test_a_chunk_with_no_matching_item_contributes_no_rows(monkeypatch, chunks):
    monkeypatch.setattr(table, "extract_one", lambda text, columns, model: fake_rows([]))

    assert table.run(chunks, COLUMNS, model=None) == []


def test_a_model_failure_on_one_chunk_fails_the_run(monkeypatch, chunks):
    def boom(text, columns, model):
        if text.endswith("3"):
            raise RuntimeError("model refused")
        return fake_rows([["item", "2027"]])

    monkeypatch.setattr(settings, "llm_concurrency", 4)
    monkeypatch.setattr(table, "extract_one", boom)

    with pytest.raises(RuntimeError, match="model refused"):
        table.run(chunks, COLUMNS, model=None)


def test_propose_columns_returns_name_and_description_per_column(monkeypatch):
    seen = {}

    class FakeModel:
        def with_structured_output(self, schema):
            seen["schema"] = schema
            return self

        def invoke(self, messages):
            seen["messages"] = messages
            return table.ProposedColumns(columns=[table.Column(name="Kewajiban", description="The obligation")])

    monkeypatch.setattr(table, "llm", lambda model=None: FakeModel())

    assert table.propose_columns("setiap kewajiban dan tenggatnya", model=None) == [
        {"name": "Kewajiban", "description": "The obligation"},
    ]
    assert "setiap kewajiban dan tenggatnya" in seen["messages"][-1][1]
