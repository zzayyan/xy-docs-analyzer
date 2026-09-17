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


SECTIONS = [{"title": f"Bab {i} " + "j" * 400, "id": f"s{i}"} for i in range(60)]


def test_document_context_carries_outline_titles_and_chunk_text_and_stays_bounded():
    chunks = [{"id": f"f:{i}", "text": f"isi {i} " + "x" * 5000, "pages": [i], "headings": []} for i in range(20)]

    context = table.document_context(SECTIONS, chunks)

    assert "Bab 0" in context and "isi 0" in context
    assert "j" * 400 not in context, "a long heading is truncated"
    assert "Bab 59" not in context, "the outline is truncated"
    assert "isi 19" not in context, "only the first chunks are used"
    assert len(context) < 10000, f"context is {len(context)} characters, too long to prepend to every proposal"


def test_document_context_of_a_short_document_is_its_chunks_alone():
    # A short document has no sections, so the passages are all the context there is
    context = table.document_context([], [{"id": "f:0", "text": "isi", "pages": [1], "headings": []}])

    assert "isi" in context


def test_propose_columns_passes_the_document_context_to_the_model(monkeypatch):
    seen = {}

    class FakeModel:
        def with_structured_output(self, schema):
            return self

        def invoke(self, messages):
            seen["messages"] = messages
            return table.ProposedColumns(columns=[table.Column(name="Pasal", description="Nomor pasal")])

    monkeypatch.setattr(table, "llm", lambda model=None: FakeModel())

    table.propose_columns("setiap kewajiban", model=None, context="Outline:\n- Bab I Ketentuan Umum")

    prompt = "\n".join(text for _, text in seen["messages"])
    assert "Bab I Ketentuan Umum" in prompt
    assert "setiap kewajiban" in prompt


def test_suggest_tables_returns_candidate_tables_with_their_columns(monkeypatch):
    seen = {}

    class FakeModel:
        def with_structured_output(self, schema):
            return self

        def invoke(self, messages):
            seen["messages"] = messages
            return table.SuggestedTables(tables=[
                table.SuggestedTable(title="Kewajiban", columns=[table.Column(name="Pasal", description="Nomor pasal")]),
            ])

    monkeypatch.setattr(table, "llm", lambda model=None: FakeModel())

    assert table.suggest_tables("Outline:\n- Bab I", model=None) == [
        {"title": "Kewajiban", "columns": [{"name": "Pasal", "description": "Nomor pasal"}]},
    ]
    assert "Bab I" in "\n".join(text for _, text in seen["messages"])
