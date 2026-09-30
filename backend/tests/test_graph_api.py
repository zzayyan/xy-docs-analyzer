"""HTTP API for the Graph tab. The store is faked, so no Neo4j needed (prior art: test_table_api.py)."""
import pytest
from fastapi.testclient import TestClient

import app.store as store_module
from app.api import app

client = TestClient(app)

REGION = {"page": 3, "l": 0, "t": 0, "r": 10, "b": 10, "page_width": 600, "page_height": 800}


@pytest.fixture
def stubbed(monkeypatch):
    monkeypatch.setattr(store_module, "get_file", lambda doc_id: {"id": doc_id, "name": "d.pdf", "status": "done"})
    entities = {"yolov8": {"key": "yolov8", "name": "YOLOv8", "type": "Product", "mentions": 24},
                "100.3/96/2025": {"key": "100.3/96/2025", "name": "100.3/96/2025", "type": "Regulation", "mentions": 1}}
    seen = {}

    def graph_top(file_id, limit):
        seen["limit"] = limit
        return {"nodes": list(entities.values()), "edges": [{"source": "yolov8", "target": "100.3/96/2025", "type": "CITES"}], "total": 1103}

    monkeypatch.setattr(store_module, "graph_top", graph_top)
    monkeypatch.setattr(store_module, "entity", lambda file_id, key: entities.get(key))
    monkeypatch.setattr(store_module, "entity_neighbours", lambda file_id, key, limit: [
        {"key": "bisindo", "name": "BISINDO", "type": "Concept", "mentions": 43, "rel": "DETECTS", "outgoing": True},
        {"key": "ultralytics", "name": "Ultralytics", "type": "Organization", "mentions": 3, "rel": "DEVELOPED", "outgoing": False},
    ])
    monkeypatch.setattr(store_module, "entity_chunks", lambda file_id, key, limit: [
        {"id": "f:7", "text": "YOLOv8 is ...", "pages": [3], "headings": ["2.1.4 YOLOv8"], "regions": [REGION]},
    ])
    return seen


def test_the_graph_is_the_top_entities_with_the_edges_between_them(stubbed):
    body = client.get("/documents/d1/graph").json()

    assert [n["name"] for n in body["nodes"]] == ["YOLOv8", "100.3/96/2025"]
    assert body["edges"] == [{"source": "yolov8", "target": "100.3/96/2025", "type": "CITES"}]
    assert body["total"] == 1103
    assert stubbed["limit"] == 120


def test_an_entity_brings_its_neighbours_edges_both_ways_and_citations_the_source_panel_opens(stubbed):
    body = client.get("/documents/d1/graph/entity", params={"key": "yolov8"}).json()

    assert body["entity"]["name"] == "YOLOv8"
    assert [n["key"] for n in body["nodes"]] == ["bisindo", "ultralytics"]
    assert body["edges"] == [
        {"source": "yolov8", "target": "bisindo", "type": "DETECTS"},
        {"source": "ultralytics", "target": "yolov8", "type": "DEVELOPED"},
    ]
    [citation] = body["citations"]
    assert (citation["n"], citation["source"], citation["pages"], citation["regions"]) == (1, "kg", [3], [REGION])


def test_an_entity_named_with_slashes_is_found_and_an_unknown_one_is_404(stubbed):
    assert client.get("/documents/d1/graph/entity", params={"key": "100.3/96/2025"}).status_code == 200
    assert client.get("/documents/d1/graph/entity", params={"key": "nope"}).status_code == 404


def test_an_unknown_document_has_no_graph(monkeypatch):
    monkeypatch.setattr(store_module, "get_file", lambda doc_id: None)
    assert client.get("/documents/nope/graph").status_code == 404
