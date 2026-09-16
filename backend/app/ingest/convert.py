from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import pypdfium2
from docling.chunking import HybridChunker
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling_core.types.doc.document import DoclingDocument
from transformers import AutoTokenizer

from app.config import settings

PDF_BATCH_PAGES = 25
TEXT_LAYER_CHARS = 100
TEXT_LAYER_SAMPLE = 10


@lru_cache
def converter(ocr: bool = True) -> DocumentConverter:
    options = PdfPipelineOptions(do_ocr=ocr)
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})


def has_text_layer(path: str) -> bool:
    """Whether the PDF carries its own text, sampled across the document."""
    pdf = pypdfium2.PdfDocument(path)
    try:
        step = max(1, len(pdf) // TEXT_LAYER_SAMPLE)
        sampled = [len(pdf[i].get_textpage().get_text_range().strip()) for i in range(0, len(pdf), step)]
        return sum(sampled) / len(sampled) > TEXT_LAYER_CHARS
    finally:
        pdf.close()


@lru_cache
def tokenizer() -> HuggingFaceTokenizer:
    # Same tokenizer as the embedding model, so chunk sizes match what bge-m3 sees
    return HuggingFaceTokenizer(
        tokenizer=AutoTokenizer.from_pretrained(settings.tokenizer_model),
        max_tokens=settings.chunk_max_tokens,
    )


def page_count(path: str) -> int:
    """Pages in a PDF, cheap enough to run before deciding whether to ingest it at all."""
    pdf = pypdfium2.PdfDocument(path)
    try:
        return len(pdf)
    finally:
        pdf.close()


def convert_document(path: str, on_progress: Callable[[int, int], None] | None = None) -> DoclingDocument:
    if Path(path).suffix.lower() != ".pdf":
        return converter().convert(path).document
    # Docling's memory keeps growing within one convert() call: 25 pages peak at ~14 GB, 100 pages exhausted
    # Windows commit memory and killed the API worker with an access violation. Batches start at page 1 and
    # stay contiguous so concatenate() keeps absolute page numbers.
    # ponytail: a batch whose first page fails to convert shifts later page numbers by one in the merged doc
    total = page_count(path)
    # OCR on a born-digital PDF costs ~70% more time and added 8 characters across 60 measured pages
    pdf_converter = converter(ocr=not has_text_layer(path))
    docs = []
    for start in range(1, total + 1, PDF_BATCH_PAGES):
        end = min(start + PDF_BATCH_PAGES - 1, total)
        docs.append(pdf_converter.convert(path, page_range=(start, end)).document)
        # Conversion is the longest stage by far, so report pages as each batch lands
        if on_progress:
            on_progress(end, total)
    return DoclingDocument.concatenate(docs)


def convert(path: str, on_progress: Callable[[int, int], None] | None = None) -> tuple[DoclingDocument, int, list[dict]]:
    """Convert a file and return (document, total token count, chunks)."""
    doc = convert_document(path, on_progress)
    tokens = tokenizer().count_tokens(doc.export_to_markdown())

    chunker = HybridChunker(tokenizer=tokenizer(), merge_peers=True)
    chunks = []
    for idx, chunk in enumerate(chunker.chunk(dl_doc=doc)):
        pages = sorted({prov.page_no for item in chunk.meta.doc_items for prov in item.prov})
        chunks.append({
            "idx": idx,
            # contextualize() prepends headings, which helps both embedding and answering
            "text": chunker.contextualize(chunk=chunk),
            "pages": pages,
            "headings": chunk.meta.headings or [],
        })
    return doc, tokens, chunks
