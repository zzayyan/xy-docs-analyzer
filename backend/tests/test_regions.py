"""Regions are JSON-encoded on the Chunk node. Neo4j faked."""
import json

import pytest
from docling_core.types.doc.document import DoclingDocument

import app.graph as graph_mod
from app.config import settings


class Recorder:
    def __init__(self, rows: list[dict]):
        self.rows = rows

    def query(self, statement: str, params: dict) -> list[dict]:
        return self.rows


REGION = {"page": 1, "l": 0, "t": 0, "r": 10, "b": 10, "page_width": 600, "page_height": 800}


def test_contexts_decodes_regions_and_tags_the_source():
    rows = [
        {"id": "f:0", "text": "t", "pages": [1], "headings": [], "regions": json.dumps([REGION])},
        {"id": "f:1", "text": "t2", "pages": [], "headings": [], "regions": None},
    ]

    contexts = graph_mod._contexts(rows, "vector")

    assert [c["regions"] for c in contexts] == [[REGION], []]
    assert all(c["source"] == "vector" for c in contexts)


def test_ingest_writes_each_chunks_regions_to_neo4j_as_json(monkeypatch, tmp_path):
    import app.ingest.pipeline as pipeline

    written: list[tuple[str, dict]] = []

    class Graph:
        def query(self, statement: str, params: dict) -> list:
            written.append((statement, params))
            return [{"n": 1}] if "count(f)" in statement else []

    chunks = [
        {"idx": 0, "text": "a", "pages": [1], "headings": [], "regions": [REGION]},
        {"idx": 1, "text": "b", "pages": [], "headings": [], "regions": []},
    ]
    monkeypatch.setattr(pipeline, "graph", lambda: Graph())
    monkeypatch.setattr(pipeline, "convert", lambda path, scanned, on_progress=None: (DoclingDocument(name="doc"), 10, chunks))
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(pipeline, "scanned_pages", lambda path: set())
    monkeypatch.setattr(pipeline, "embeddings", lambda: type("E", (), {"embed_documents": lambda self, texts: [[0.0]] * len(texts)})())

    pipeline.ingest("f", "doc.pdf")

    [(statement, params)] = [(s, p) for s, p in written if "MERGE (c:Chunk" in s]
    assert "c.regions = r.regions" in statement
    assert [json.loads(r["regions"]) for r in params["rows"]] == [[REGION], []]


def test_a_document_deleted_mid_ingest_stops_it_without_an_error(monkeypatch):
    import app.ingest.pipeline as pipeline

    written: list[str] = []

    class Graph:  # the File is already gone: every status write matches nothing
        def query(self, statement: str, params: dict) -> list:
            written.append(statement)
            return [{"n": 0}] if "count(f)" in statement else []

    monkeypatch.setattr(pipeline, "graph", lambda: Graph())
    monkeypatch.setattr(pipeline, "convert", lambda path, scanned, on_progress=None: pytest.fail("converted a deleted document"))

    pipeline.ingest("f", "doc.pdf")

    assert len(written) == 1, "stopped at the first status write, no error status attempted"



def test_ingest_records_the_document_language_and_survives_failing_to_detect_it(monkeypatch, tmp_path):
    import app.ingest.pipeline as pipeline

    statuses: list[dict] = []

    class Graph:
        def query(self, statement: str, params: dict) -> list:
            if "count(f)" in statement:
                statuses.append(params["props"])
                return [{"n": 1}]
            return []

    class Model:
        def __init__(self, answer):
            self.answer = answer

        def with_structured_output(self, schema):
            return self

        def invoke(self, messages):
            if isinstance(self.answer, Exception):
                raise self.answer
            return pipeline.DocumentLanguage(language=self.answer)

    chunks = [{"idx": 0, "text": "Pasal 1 Pihak pertama wajib membayar", "pages": [1], "headings": [], "regions": []}]
    monkeypatch.setattr(pipeline, "graph", lambda: Graph())
    monkeypatch.setattr(pipeline, "convert", lambda path, scanned, on_progress=None: (DoclingDocument(name="doc"), 10, chunks))
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(pipeline, "scanned_pages", lambda path: set())
    monkeypatch.setattr(pipeline, "embeddings", lambda: type("E", (), {"embed_documents": lambda self, texts: [[0.0]] * len(texts)})())

    for answer, expected in (("Indonesian ", "Indonesian"), (RuntimeError("model down"), None)):
        statuses.clear()
        monkeypatch.setattr(pipeline, "llm", lambda model=None, a=answer: Model(a))

        pipeline.ingest("f", "doc.pdf")

        [embedding] = [s for s in statuses if s.get("status") == "embedding"]
        assert embedding["language"] == expected
        assert statuses[-1]["status"] == "done", "an undetected language never fails the ingest"


def test_ingest_keeps_each_chunks_refs_and_the_converted_document(monkeypatch, tmp_path):
    import app.ingest.pipeline as pipeline
    from docling_core.types.doc.labels import DocItemLabel

    written: list[tuple[str, dict]] = []

    class Graph:
        def query(self, statement: str, params: dict) -> list:
            written.append((statement, params))
            return [{"n": 1}] if "count(f)" in statement else []

    doc = DoclingDocument(name="kontrak")
    doc.add_text(label=DocItemLabel.TEXT, text="Denda 2% per bulan.")
    chunks = [{"idx": 0, "text": "Denda 2% per bulan.", "pages": [], "headings": [], "regions": [], "refs": ["#/texts/0"]}]
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(pipeline, "graph", lambda: Graph())
    monkeypatch.setattr(pipeline, "convert", lambda path, scanned, on_progress=None: (doc, 10, chunks))
    monkeypatch.setattr(pipeline, "scanned_pages", lambda path: set())
    monkeypatch.setattr(pipeline, "embeddings", lambda: type("E", (), {"embed_documents": lambda self, texts: [[0.0]] * len(texts)})())

    pipeline.ingest("f", "kontrak.docx")

    [(statement, params)] = [(s, p) for s, p in written if "MERGE (c:Chunk" in s]
    assert "c.refs = r.refs" in statement
    assert [r["refs"] for r in params["rows"]] == [["#/texts/0"]]
    kept = DoclingDocument.load_from_json(tmp_path / "docling" / "f.json")
    assert [t.text for t in kept.texts] == ["Denda 2% per bulan."]
