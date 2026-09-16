"""OCR runs only for PDFs without their own text layer."""
from types import SimpleNamespace

import pypdfium2
import pytest
from docling_core.types.doc.document import DoclingDocument

import app.ingest.convert as convert_mod


def test_blank_pdf_has_no_text_layer(tmp_path):
    pdf = pypdfium2.PdfDocument.new()
    for _ in range(3):
        pdf.new_page(200, 200)
    path = tmp_path / "scan-like.pdf"
    pdf.save(str(path))

    assert convert_mod.has_text_layer(str(path)) is False


@pytest.mark.parametrize(("text_layer", "expect_ocr"), [(True, False), (False, True)])
def test_converter_picks_ocr_from_the_text_layer(monkeypatch, text_layer, expect_ocr):
    asked: list[bool] = []

    def fake_converter(ocr: bool = True):
        asked.append(ocr)
        return SimpleNamespace(convert=lambda path, page_range: SimpleNamespace(document=DoclingDocument(name="p")))

    monkeypatch.setattr(convert_mod, "converter", fake_converter)
    monkeypatch.setattr(convert_mod, "page_count", lambda path: 10)
    monkeypatch.setattr(convert_mod, "has_text_layer", lambda path: text_layer)

    convert_mod.convert_document("doc.pdf")

    assert asked == [expect_ocr]
