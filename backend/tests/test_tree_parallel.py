"""Section summaries run in parallel, keep document order, and skip the LLM for container headings."""
import threading
import time
from types import SimpleNamespace

import pytest

import app.ingest.tree as tree
from app.config import settings


@pytest.fixture
def tree_input():
    sections = [{"id": f"f:s{i}", "title": f"Bab {i}", "parent": None} for i in range(6)]
    # s5 is a container: no chunk points at it, so it must be described by its children instead
    sections[5]["parent"] = None
    sections[0]["parent"] = "f:s5"
    chunks = [{"id": f"f:c{i}", "text": f"isi {i}"} for i in range(5)]
    chunk_section = {f"f:c{i}": f"f:s{i}" for i in range(5)}
    return sections, chunks, chunk_section


def test_summaries_run_concurrently_and_stay_in_order(monkeypatch, tree_input):
    sections, chunks, chunk_section = tree_input
    threads: set[int] = set()

    class SlowLLM:
        def invoke(self, messages):
            threads.add(threading.get_ident())
            time.sleep(0.2)
            return SimpleNamespace(content=f"  ringkasan {messages[1][1].splitlines()[0]}  ")

    monkeypatch.setattr(settings, "llm_concurrency", 4)
    monkeypatch.setattr(tree, "llm", lambda: SlowLLM())

    progress: list[tuple[int, int]] = []
    started = time.time()
    tree.summarize_sections(sections, chunks, chunk_section, on_progress=lambda d, t: progress.append((d, t)))
    elapsed = time.time() - started

    assert len(threads) > 1, "summaries did not run in parallel"
    assert elapsed < 5 * 0.2, f"took {elapsed:.1f}s, no faster than sequential"
    assert [s["summary"] for s in sections[:5]] == [f"ringkasan Section: Bab {i}" for i in range(5)]
    assert progress == [(i, 6) for i in range(1, 7)]


def test_container_section_is_described_without_an_llm_call(monkeypatch, tree_input):
    sections, chunks, chunk_section = tree_input

    class CountingLLM:
        calls = 0

        def invoke(self, messages):
            CountingLLM.calls += 1
            return SimpleNamespace(content="ringkasan")

    monkeypatch.setattr(settings, "llm_concurrency", 4)
    monkeypatch.setattr(tree, "llm", lambda: CountingLLM())

    tree.summarize_sections(sections, chunks, chunk_section)

    assert sections[5]["summary"] == "Contains: Bab 0"
    assert CountingLLM.calls == 5, "one call per section with text, none for the container"
