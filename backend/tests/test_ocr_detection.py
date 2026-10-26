"""OCR runs only for the PDF page batches that hold a page without its own text layer."""
from types import SimpleNamespace

import pypdfium2
from docling_core.types.doc.document import DoclingDocument

import app.ingest.convert as convert_mod


def test_blank_pages_count_as_scanned(tmp_path):
    pdf = pypdfium2.PdfDocument.new()
    for _ in range(3):
        pdf.new_page(200, 200)
    path = tmp_path / "scan-like.pdf"
    pdf.save(str(path))

    assert convert_mod.scanned_pages(str(path)) == {1, 2, 3}


def test_a_non_pdf_is_never_opened_as_a_pdf():
    assert convert_mod.scanned_pages("notes.md") == set()


def test_only_batches_holding_a_scanned_page_run_ocr(monkeypatch):
    asked: list[tuple[tuple[int, int], bool]] = []

    def fake_converter(ocr: bool = True):
        def convert(path, page_range):
            asked.append((page_range, ocr))
            return SimpleNamespace(document=DoclingDocument(name="p"))
        return SimpleNamespace(convert=convert)

    monkeypatch.setattr(convert_mod, "converter", fake_converter)
    monkeypatch.setattr(convert_mod, "page_count", lambda path: 60)

    convert_mod.convert_document("mixed.pdf", scanned={30, 31})

    assert asked == [((1, 25), False), ((26, 50), True), ((51, 60), False)]
