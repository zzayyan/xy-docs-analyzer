"""The embedding-model guard in app.db. Neo4j faked."""
import pytest

from app.config import settings
from app.db import check_embedding_model


class FakeGraph:
    """Minimal stand-in for Neo4jGraph: canned marker and chunk count, records the statements it runs."""

    def __init__(self, model: str, dim: int, chunks: int = 0, stored_dim: int | None = None):
        self.marker = {"model": model, "dim": dim}
        self.chunks = chunks
        self.stored_dim = stored_dim if stored_dim is not None else dim
        self.statements: list[str] = []

    def query(self, statement: str, params: dict | None = None) -> list[dict]:
        self.statements.append(" ".join(statement.split()))
        if "MERGE (m:Meta" in statement:
            return [dict(self.marker)]
        if "size(c.embedding)" in statement:
            return [{"dim": self.stored_dim}] if self.chunks else []
        if "count(c)" in statement:
            return [{"n": self.chunks}]
        if "SET m.model" in statement:
            self.marker = {"model": params["model"], "dim": params["dim"]}
        return []


@pytest.fixture
def active(monkeypatch):
    monkeypatch.setattr(settings, "embed_model", "bge-m3")
    monkeypatch.setattr(settings, "embed_dim", 1024)
    return "bge-m3", 1024


def test_same_model_passes(active):
    g = FakeGraph(*active, chunks=42)
    check_embedding_model(g)


def test_switching_model_with_stored_chunks_fails_loudly(active):
    g = FakeGraph("nvidia/nemotron-3-embed-1b:free", 2048, chunks=7)
    with pytest.raises(RuntimeError, match="7 chunks"):
        check_embedding_model(g)
    assert g.marker["model"] != "bge-m3", "must not adopt the new model while old vectors exist"


def test_switching_model_on_empty_database_adopts_the_new_model(active):
    g = FakeGraph("nvidia/nemotron-3-embed-1b:free", 2048, chunks=0)
    check_embedding_model(g)
    assert g.marker == {"model": "bge-m3", "dim": 1024}


def test_same_model_different_dimension_is_caught(active):
    g = FakeGraph("bge-m3", 768, chunks=3)
    with pytest.raises(RuntimeError, match="768 dims"):
        check_embedding_model(g)


def test_vectors_left_by_an_older_config_are_caught(active):
    # Marker says the active model, but the stored vectors were written before the marker existed
    g = FakeGraph(*active, chunks=127, stored_dim=2048)
    with pytest.raises(RuntimeError, match="127 chunks"):
        check_embedding_model(g)
