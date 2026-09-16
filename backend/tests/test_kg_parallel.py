"""Parallel KG extraction must keep chunk order and write once per chunk. No Neo4j or LLM needed."""
import threading
import time
from types import SimpleNamespace

import pytest

import app.ingest.kg as kg
from app.config import settings


class Recorder:
    def __init__(self):
        self.writes: list[tuple[str, str]] = []

    def query(self, statement: str, params: dict) -> list:
        self.writes.append((("entities" if "UNWIND $entities" in statement else "relationships"), params["chunk_id"]))
        return []


@pytest.fixture
def chunks():
    return [{"id": f"f:{i}", "text": f"text {i}"} for i in range(8)]


def fake_doc(text: str):
    node = SimpleNamespace(id=f"Entity {text[-1]}", type="Concept")
    return SimpleNamespace(nodes=[node], relationships=[])


def test_extraction_runs_concurrently_and_writes_in_chunk_order(monkeypatch, chunks):
    threads: set[int] = set()

    def slow_extract(text: str):
        threads.add(threading.get_ident())
        time.sleep(0.2)
        return fake_doc(text)

    recorder = Recorder()
    monkeypatch.setattr(settings, "llm_concurrency", 4)
    monkeypatch.setattr(kg, "extract_one", slow_extract)
    monkeypatch.setattr(kg, "graph", lambda: recorder)

    progress: list[tuple[int, int]] = []
    started = time.time()
    kg.extract_graph("f", chunks, on_progress=lambda done, total: progress.append((done, total)))
    elapsed = time.time() - started

    assert len(threads) > 1, "extraction did not run in parallel"
    assert elapsed < 8 * 0.2, f"took {elapsed:.1f}s, no faster than sequential"
    assert [chunk_id for kind, chunk_id in recorder.writes if kind == "entities"] == [c["id"] for c in chunks]
    assert progress == [(i, 8) for i in range(1, 9)]


def test_a_failing_chunk_aborts_the_ingest(monkeypatch, chunks):
    def boom(text: str):
        if text.endswith("3"):
            raise RuntimeError("model refused")
        return fake_doc(text)

    monkeypatch.setattr(settings, "llm_concurrency", 4)
    monkeypatch.setattr(kg, "extract_one", boom)
    monkeypatch.setattr(kg, "graph", lambda: Recorder())

    with pytest.raises(RuntimeError, match="model refused"):
        kg.extract_graph("f", chunks)
