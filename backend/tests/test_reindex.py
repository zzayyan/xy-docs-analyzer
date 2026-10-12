"""Switching the embedding model from Settings. Neo4j and the embedding servers are faked."""
import pytest
from fastapi.testclient import TestClient

import app.api as api_module
from app import model_settings, reindex
from app.api import app

client = TestClient(app)

FORM = {"embed_provider": "ollama", "embed_base_url": "http://localhost:11434", "embed_model": "new-model", "embed_dim": 3}


class FakeGraph:
    """Chunks of two documents embedded with old-model, and the marker saying so."""

    def __init__(self):
        self.chunks = {f"{f}:{i}": {"file_id": f, "text": f"text {f} {i}", "embedding": [0.0, 0.0]} for f in ("a", "b") for i in range(2)}
        self.marker = {"model": "old-model", "dim": 2}
        self.in_flight = 0

    def query(self, statement: str, params: dict | None = None) -> list:
        params = params or {}
        if statement == reindex.EMBEDDED:
            return [{"n": sum("embedding" in c for c in self.chunks.values())}]
        if statement == reindex.MARKER:
            return [self.marker]
        if statement == reindex.SET_MARKER:
            self.marker = dict(params)
        elif statement == reindex.IN_FLIGHT:
            return [{"n": self.in_flight}]
        elif statement == reindex.FILES:
            return [{"id": f} for f in sorted({c["file_id"] for c in self.chunks.values()})]
        elif statement == reindex.FILE_CHUNKS:
            return [{"id": i, "text": c["text"]} for i, c in self.chunks.items() if c["file_id"] == params["id"]]
        elif statement == reindex.WRITE_NEXT:
            for row in params["rows"]:
                self.chunks[row["id"]]["embedding_next"] = row["vector"]
        elif statement == reindex.SWAP:
            for c in self.chunks.values():
                if "embedding_next" in c:
                    c["embedding"] = c.pop("embedding_next")
        elif statement == reindex.CLEAR_NEXT:
            for c in self.chunks.values():
                c.pop("embedding_next", None)
        return []


class FakeEmbeddings:
    def __init__(self, dim: int, fail_on: str | None = None):
        self.dim, self.fail_on = dim, fail_on

    def embed_query(self, text):
        return [1.0] * self.dim

    def embed_documents(self, texts):
        if self.fail_on and any(self.fail_on in t for t in texts):
            raise ConnectionError("embedding server went away")
        return [[1.0] * self.dim for _ in texts]


@pytest.fixture
def db(monkeypatch):
    g = FakeGraph()
    saved: list[dict] = []
    monkeypatch.setattr(reindex, "graph", lambda: g)
    monkeypatch.setattr(model_settings, "save", lambda group, values: saved.append(values))
    monkeypatch.setattr(model_settings, "saved", lambda group, g=None: {})
    monkeypatch.setattr(reindex, "embedding_model", lambda *args: FakeEmbeddings(3))
    monkeypatch.setitem(reindex.STATE, "status", "idle")
    g.saved = saved
    return g


def test_another_model_needs_a_reindex_once_vectors_are_stored(db):
    response = client.put("/settings/embedding", json=FORM)
    assert response.status_code == 409
    assert db.saved == []
    assert db.marker["model"] == "old-model"


def test_another_server_for_the_same_model_saves_at_once(db):
    response = client.put("/settings/embedding", json={**FORM, "embed_model": "old-model", "embed_dim": 2})
    assert response.status_code == 200, response.text
    assert db.saved[0]["embed_model"] == "old-model"


def test_an_empty_database_adopts_another_model_at_once(db):
    db.chunks.clear()
    assert client.put("/settings/embedding", json=FORM).status_code == 200
    assert db.marker == {"model": "new-model", "dim": 3}


def test_a_reindex_embeds_every_chunk_then_switches_in_one_go(db):
    response = client.put("/settings/embedding", json={**FORM, "reindex": True})
    assert response.status_code == 200, response.text
    # TestClient runs the background task before returning
    assert reindex.STATE == {"status": "done", "done": 2, "total": 2, "error": None}
    assert all(c["embedding"] == [1.0, 1.0, 1.0] and "embedding_next" not in c for c in db.chunks.values())
    assert db.marker == {"model": "new-model", "dim": 3}
    assert db.saved[0]["embed_model"] == "new-model"


def test_a_failed_reindex_leaves_the_old_vectors_and_settings(db, monkeypatch):
    monkeypatch.setattr(reindex, "embedding_model", lambda *args: FakeEmbeddings(3, fail_on="text b"))
    client.put("/settings/embedding", json={**FORM, "reindex": True})
    assert reindex.STATE["status"] == "error"
    assert "went away" in reindex.STATE["error"]
    assert all(c["embedding"] == [0.0, 0.0] and "embedding_next" not in c for c in db.chunks.values())
    assert db.marker["model"] == "old-model"
    assert db.saved == []


def test_a_wrong_dimension_is_refused_before_any_chunk_is_read(db, monkeypatch):
    monkeypatch.setattr(reindex, "embedding_model", lambda *args: FakeEmbeddings(1024))
    response = client.put("/settings/embedding", json={**FORM, "reindex": True})
    assert response.status_code == 400
    assert "1024" in response.json()["detail"]
    assert reindex.STATE["status"] == "idle"


def test_no_reindex_while_documents_are_ingesting_and_no_upload_while_reindexing(db, monkeypatch):
    db.in_flight = 1
    assert client.put("/settings/embedding", json={**FORM, "reindex": True}).status_code == 409

    monkeypatch.setitem(reindex.STATE, "status", "running")
    assert client.post("/documents", files={"file": ("a.md", b"# a", "text/markdown")}).status_code == 409
    monkeypatch.setattr(api_module.store, "get_file", lambda doc_id: {"id": doc_id, "status": "error"})
    assert client.post("/documents/d1/retry").status_code == 409
