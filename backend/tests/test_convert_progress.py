"""Conversion reports progress per page batch. Docling itself is stubbed, so no models are loaded."""
from types import SimpleNamespace

import pytest
from docling_core.types.doc.document import DoclingDocument

import app.ingest.convert as convert_mod


@pytest.fixture
def stub_docling(monkeypatch):
    converted: list[tuple[int, int]] = []

    class FakeConverter:
        def convert(self, path, page_range=(1, 10**9)):
            converted.append(page_range)
            return SimpleNamespace(document=DoclingDocument(name=f"part-{page_range[0]}"))

    monkeypatch.setattr(convert_mod, "converter", lambda ocr=True: FakeConverter())
    monkeypatch.setattr(convert_mod, "has_text_layer", lambda path: True)
    return converted


def test_progress_is_reported_after_each_batch(monkeypatch, stub_docling):
    monkeypatch.setattr(convert_mod, "page_count", lambda path: 100)
    seen: list[tuple[int, int]] = []

    convert_mod.convert_document("doc.pdf", on_progress=lambda done, total: seen.append((done, total)))

    assert stub_docling == [(1, 25), (26, 50), (51, 75), (76, 100)]
    assert seen == [(25, 100), (50, 100), (75, 100), (100, 100)]


def test_last_batch_stops_at_the_final_page(monkeypatch, stub_docling):
    monkeypatch.setattr(convert_mod, "page_count", lambda path: 30)
    seen: list[tuple[int, int]] = []

    convert_mod.convert_document("doc.pdf", on_progress=lambda done, total: seen.append((done, total)))

    assert stub_docling == [(1, 25), (26, 30)]
    assert seen == [(25, 30), (30, 30)]


def test_non_pdf_takes_the_single_call_path(monkeypatch, stub_docling):
    convert_mod.convert_document("notes.md", on_progress=lambda done, total: pytest.fail("should not batch"))
    assert stub_docling == [(1, 10**9)]
