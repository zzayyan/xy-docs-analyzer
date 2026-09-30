"""Regions are JSON-encoded on the Chunk node, the same reason Turn.citations and TableExtraction's
columns/rows are (a Neo4j property can't hold a list of maps). No real Neo4j needed."""
import json

import app.graph as graph_mod
import app.store as store_module


class Recorder:
    def __init__(self, rows: list[dict]):
        self.rows = rows

    def query(self, statement: str, params: dict) -> list[dict]:
        return self.rows


REGION = {"page": 1, "l": 0, "t": 0, "r": 10, "b": 10, "page_width": 600, "page_height": 800}


def test_list_chunks_decodes_a_json_regions_string(monkeypatch):
    monkeypatch.setattr(store_module, "graph", lambda: Recorder(
        [{"id": "f:0", "text": "t", "pages": [1], "headings": [], "regions": json.dumps([REGION])}]
    ))

    [chunk] = store_module.list_chunks("f")

    assert chunk["regions"] == [REGION]


def test_list_chunks_treats_a_missing_regions_property_as_no_highlight(monkeypatch):
    # A chunk written before this feature shipped: Neo4j returns the property as None
    monkeypatch.setattr(store_module, "graph", lambda: Recorder(
        [{"id": "f:0", "text": "t", "pages": [1], "headings": [], "regions": None}]
    ))

    assert store_module.list_chunks("f")[0]["regions"] == []


def test_contexts_decodes_regions_and_tags_the_source():
    rows = [
        {"id": "f:0", "text": "t", "pages": [1], "headings": [], "regions": json.dumps([REGION])},
        {"id": "f:1", "text": "t2", "pages": [], "headings": [], "regions": None},
    ]

    contexts = graph_mod._contexts(rows, "vector")

    assert [c["regions"] for c in contexts] == [[REGION], []]
    assert all(c["source"] == "vector" for c in contexts)


def test_ingest_writes_each_chunks_regions_to_neo4j_as_json(monkeypatch):
    """Conversion output faked: whatever regions convert() hands back reach the Chunk node, encoded,
    and a chunk with none is written as an empty list rather than skipped."""
    import app.ingest.pipeline as pipeline

    written: list[tuple[str, dict]] = []

    class Graph:
        def query(self, statement: str, params: dict) -> list:
            written.append((statement, params))
            return []

    chunks = [
        {"idx": 0, "text": "a", "pages": [1], "headings": [], "regions": [REGION]},
        {"idx": 1, "text": "b", "pages": [], "headings": [], "regions": []},
    ]
    monkeypatch.setattr(pipeline, "graph", lambda: Graph())
    monkeypatch.setattr(pipeline, "convert", lambda path, on_progress=None: (None, 10, chunks))
    monkeypatch.setattr(pipeline, "embeddings", lambda: type("E", (), {"embed_documents": lambda self, texts: [[0.0]] * len(texts)})())

    pipeline.ingest("f", "doc.pdf")

    [(statement, params)] = [(s, p) for s, p in written if "MERGE (c:Chunk" in s]
    assert "c.regions = r.regions" in statement
    assert [json.loads(r["regions"]) for r in params["rows"]] == [[REGION], []]
