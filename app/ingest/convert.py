from functools import lru_cache
from pathlib import Path

import pypdfium2
from docling.chunking import HybridChunker
from docling.document_converter import DocumentConverter
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling_core.types.doc.document import DoclingDocument
from transformers import AutoTokenizer

from app.config import settings

PDF_BATCH_PAGES = 25


@lru_cache
def converter() -> DocumentConverter:
    return DocumentConverter()


@lru_cache
def tokenizer() -> HuggingFaceTokenizer:
    # Same tokenizer as the embedding model, so chunk sizes match what bge-m3 sees
    return HuggingFaceTokenizer(
        tokenizer=AutoTokenizer.from_pretrained(settings.tokenizer_model),
        max_tokens=settings.chunk_max_tokens,
    )


def convert_document(path: str) -> DoclingDocument:
    if Path(path).suffix.lower() != ".pdf":
        return converter().convert(path).document
    # Docling's memory keeps growing within one convert() call: 25 pages peak at ~14 GB, 100 pages exhausted
    # Windows commit memory and killed the API worker with an access violation. Batches start at page 1 and
    # stay contiguous so concatenate() keeps absolute page numbers.
    # ponytail: a batch whose first page fails to convert shifts later page numbers by one in the merged doc
    pdf = pypdfium2.PdfDocument(path)
    total = len(pdf)
    pdf.close()
    docs = [
        converter().convert(path, page_range=(start, min(start + PDF_BATCH_PAGES - 1, total))).document
        for start in range(1, total + 1, PDF_BATCH_PAGES)
    ]
    return DoclingDocument.concatenate(docs)


def convert(path: str) -> tuple[DoclingDocument, int, list[dict]]:
    """Convert a file and return (document, total token count, chunks)."""
    doc = convert_document(path)
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
