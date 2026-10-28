"""The table_query node: a spreadsheet question the backend computes, cited first. LLM and tables faked."""
import app.graph as graph_module
import app.retrieval.table as table_module
from app.retrieval.table import Table, TableOperation

PAKET = Table.from_grid("Paket", "#/tables/0", [["paket", "harga"], ["Basic", "100000"], ["Pro", "250000"]])


class FakeLLM:
    """Structured output answers with the operation given, or raises it."""

    def __init__(self, operation: TableOperation | Exception, seen: list | None = None):
        self.operation = operation
        self.seen = seen if seen is not None else []

    def with_structured_output(self, schema):
        fake = self

        class Structured:
            def invoke(self, messages):
                fake.seen.append(messages)
                if isinstance(fake.operation, Exception):
                    raise fake.operation
                return fake.operation

        return Structured()


def ask(monkeypatch, operation, seen=None) -> list[dict]:
    monkeypatch.setattr(table_module, "load_tables", lambda doc_id: [PAKET])
    monkeypatch.setattr(table_module, "llm", lambda model=None: FakeLLM(operation, seen))
    return graph_module.table_retrieve({"doc_id": "d1", "question": "total harga semua paket?"})["retrieved"]


def test_a_spreadsheet_question_also_runs_table_query_and_other_documents_do_not():
    assert graph_module.route({"mode": "short", "spreadsheet": True}) == ["vector_retrieve", "table_query"]
    assert graph_module.route({"mode": "short"}) == ["vector_retrieve"]
    assert "table_query" not in graph_module.route({"mode": "long", "spreadsheet": False})


def test_the_computed_result_is_cited_first_with_the_rows_it_used(monkeypatch):
    seen = []
    [computed] = ask(monkeypatch, TableOperation(operation="sum", column="harga"), seen)
    vector_hit = {"id": "d1:0", "text": "Basic, harga = 100000", "pages": [], "headings": [], "regions": [],
                  "refs": ["#/tables/0/rows/1"], "source": "vector"}

    contexts = graph_module.fuse({"retrieved": [vector_hit, computed]})["contexts"]
    [first, second] = graph_module.to_citations(contexts)

    assert (first["source"], first["headings"]) == ("table", ["Paket"])
    assert "350000" in first["text"]
    assert first["refs"] == ["#/tables/0/rows/1", "#/tables/0/rows/2"]
    assert second["chunk_id"] == "d1:0"
    assert 'Sheet "Paket"' in seen[0][0][1] and "harga" in seen[0][0][1], "the model sees the table's schema"


def test_a_question_that_is_not_a_calculation_leaves_the_answer_to_vector_search(monkeypatch):
    assert ask(monkeypatch, TableOperation(operation="none")) == []


def test_an_operation_naming_a_column_the_table_lacks_or_a_failed_call_leaves_it_to_vector_search(monkeypatch):
    assert ask(monkeypatch, TableOperation(operation="sum", column="diskon")) == []
    assert ask(monkeypatch, RuntimeError("model down")) == []


def test_a_document_without_kept_tables_never_calls_the_model(monkeypatch):
    monkeypatch.setattr(table_module, "load_tables", lambda doc_id: [])
    monkeypatch.setattr(table_module, "llm", lambda model=None: (_ for _ in ()).throw(AssertionError("called the model")))

    assert graph_module.table_retrieve({"doc_id": "old", "question": "total?"})["retrieved"] == []


def test_the_answer_prompt_marks_the_computed_block_so_the_model_does_not_redo_the_arithmetic(monkeypatch):
    seen = []

    class Answering:
        def invoke(self, messages):
            seen.append(messages)
            return type("Message", (), {"content": "Totalnya 350000 [1]."})()

    monkeypatch.setattr(graph_module, "llm", lambda model=None: Answering())
    computed = {"id": "table:result", "text": "SUM(harga) = 350000 (2 rows)", "pages": [], "source": "table"}
    chunk = {"id": "d1:0", "text": "Basic, harga = 100000", "pages": [1], "source": "vector"}

    graph_module.generate({"question": "total harga?", "contexts": [computed, chunk]})

    prompt = seen[0][-1][1]
    assert "[1] (computed by the system over the whole sheet" in prompt
    assert "[2] (pages: [1])" in prompt
