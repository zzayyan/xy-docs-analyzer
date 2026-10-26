from collections.abc import Callable
from functools import lru_cache
from io import BytesIO
from pathlib import Path

import pypdfium2
from docling.chunking import HybridChunker
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.utils.locks import pypdfium2_lock
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling_core.types.doc.document import DoclingDocument, PageItem
from transformers import AutoTokenizer

from app.config import settings

PDF_BATCH_PAGES = 25
TEXT_LAYER_CHARS = 100


@lru_cache
def converter(ocr: bool = True) -> DocumentConverter:
    options = PdfPipelineOptions(do_ocr=ocr)
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})


@lru_cache
def tokenizer() -> HuggingFaceTokenizer:
    return HuggingFaceTokenizer(
        tokenizer=AutoTokenizer.from_pretrained(settings.tokenizer_model),
        max_tokens=settings.chunk_max_tokens,
    )


def page_count(path: str) -> int:
    with pypdfium2_lock:
        pdf = pypdfium2.PdfDocument(path)
        try:
            return len(pdf)
        finally:
            pdf.close()


RENDER_SCALE = 2  # ~144 DPI


def render_page(path: str, page_no: int, scale: float = RENDER_SCALE) -> bytes | None:
    with pypdfium2_lock:
        pdf = pypdfium2.PdfDocument(path)
        try:
            if not 1 <= page_no <= len(pdf):
                return None
            buffer = BytesIO()
            pdf[page_no - 1].render(scale=scale).to_pil().save(buffer, "PNG")
            return buffer.getvalue()
        finally:
            pdf.close()


def regions_of(doc_items, pages: dict[int, PageItem]) -> list[dict]:
    """Highlight boxes, top-left origin in PDF points, each with its page size for scaling."""
    regions = []
    for item in doc_items:
        for prov in item.prov:
            page = pages.get(prov.page_no)
            if page is None:
                continue
            box = prov.bbox.to_top_left_origin(page.size.height)
            # to_top_left_origin() does not guarantee t <= b
            top, bottom = sorted((box.t, box.b))
            regions.append({
                "page": prov.page_no, "l": box.l, "t": top, "r": box.r, "b": bottom,
                "page_width": page.size.width, "page_height": page.size.height,
            })
    return regions


def is_pdf(path: str) -> bool:
    return Path(path).suffix.lower() == ".pdf"


def scanned_pages(path: str) -> set[int]:
    """1-based numbers of the PDF pages without a text layer of their own, which only OCR can read."""
    if not is_pdf(path):
        return set()
    # PDFium is not thread-safe, so share Docling's lock. Never hold it around convert(), which takes it.
    with pypdfium2_lock:
        pdf = pypdfium2.PdfDocument(path)
        try:
            return {
                i + 1 for i in range(len(pdf))
                if len(pdf[i].get_textpage().get_text_range().strip()) <= TEXT_LAYER_CHARS
            }
        finally:
            pdf.close()


def convert_document(
    path: str, scanned: set[int], on_progress: Callable[[int, int], None] | None = None,
) -> DoclingDocument:
    if not is_pdf(path):
        return converter().convert(path).document
    # Docling memory grows within one convert(): 25 pages peak at ~14 GB, 100 pages killed the worker.
    # Contiguous batches from page 1 keep absolute page numbers through concatenate().
    # ponytail: a batch whose first page fails to convert shifts later page numbers by one
    total = page_count(path)
    if on_progress:
        on_progress(0, total)
    docs = []
    for start in range(1, total + 1, PDF_BATCH_PAGES):
        end = min(start + PDF_BATCH_PAGES - 1, total)
        # OCR costs ~70% more time, so only a batch holding a scanned page pays for it. Docling then OCRs only
        # the regions with no text of their own, so the batch's born-digital pages keep their text layer.
        ocr = not scanned.isdisjoint(range(start, end + 1))
        docs.append(converter(ocr=ocr).convert(path, page_range=(start, end)).document)
        if on_progress:
            on_progress(end, total)
    return DoclingDocument.concatenate(docs)


def convert(
    path: str, scanned: set[int], on_progress: Callable[[int, int], None] | None = None,
) -> tuple[DoclingDocument, int, list[dict]]:
    doc = convert_document(path, scanned, on_progress)
    tokens = tokenizer().count_tokens(doc.export_to_markdown())

    chunker = HybridChunker(tokenizer=tokenizer(), merge_peers=True)
    chunks = []
    for idx, chunk in enumerate(chunker.chunk(dl_doc=doc)):
        pages = sorted({prov.page_no for item in chunk.meta.doc_items for prov in item.prov})
        chunks.append({
            "idx": idx,
            # Prepends headings, which helps both embedding and answering
            "text": chunker.contextualize(chunk=chunk),
            "pages": pages,
            "headings": chunk.meta.headings or [],
            "regions": regions_of(chunk.meta.doc_items, doc.pages),
        })
    return doc, tokens, chunks
