import re
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
from docling_core.types.doc.document import DoclingDocument, PageItem, RefItem, SectionHeaderItem, TitleItem
from transformers import AutoTokenizer

from app.config import settings

PDF_BATCH_PAGES = 25
TEXT_LAYER_CHARS = 100
TEXT_LAYER_SAMPLE = 10
# A Markdown table's header separator, e.g. |---|:--:|
SEPARATOR = re.compile(r"[|:\- ]+")


@lru_cache
def converter(ocr: bool = True) -> DocumentConverter:
    options = PdfPipelineOptions(do_ocr=ocr)
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})


def has_text_layer(path: str) -> bool:
    """Whether the PDF carries its own text, sampled across the document."""
    # PDFium is not thread-safe: every call shares Docling's own lock, since a conversion or a page
    # render can be running on another thread. Never held around a Docling convert(), which takes it.
    with pypdfium2_lock:
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
    with pypdfium2_lock:
        pdf = pypdfium2.PdfDocument(path)
        try:
            return len(pdf)
        finally:
            pdf.close()


RENDER_SCALE = 2  # ~144 DPI: legible for a Highlight, small enough to ship over the wire


def render_page(path: str, page_no: int, scale: float = RENDER_SCALE) -> bytes | None:
    """A PDF page as a PNG, for the citation panel's Highlight view. None for a page out of range."""
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
    """One region per (item, provenance) pair: a Highlight's bounding box, top-left origin, in PDF
    points, with the page's own size attached so the frontend can scale without a second lookup.

    docling_core's to_top_left_origin() does not guarantee t <= b afterwards (its own `.height` uses
    abs() for exactly this reason) -- normalised here once, so nothing downstream has to re-sort."""
    regions = []
    for item in doc_items:
        for prov in item.prov:
            page = pages.get(prov.page_no)
            if page is None:
                continue
            box = prov.bbox.to_top_left_origin(page.size.height)
            top, bottom = sorted((box.t, box.b))
            regions.append({
                "page": prov.page_no, "l": box.l, "t": top, "r": box.r, "b": bottom,
                "page_width": page.size.width, "page_height": page.size.height,
            })
    return regions


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


def document_tables(doc: DoclingDocument) -> dict[str, dict]:
    """Every table Docling recognised, by its self_ref, whole and as Markdown: what a Table Extraction
    reads instead of the triplet text ("row, column = value") the chunker flattens it into, which also
    splits one large table across several chunks, mid-row (see docs/adr/0005). A table with no
    Markdown is left out, so its chunks keep its triplet text."""
    tables = {}
    for idx, item in enumerate(doc.tables):
        # The export puts the caption above the table (kept apart below), and pads every cell to its column's
        # widest, which costs tokens on every row of every read
        exported = item.export_to_markdown(doc).splitlines()
        lines = [" ".join(line.split()) for line in exported if line.lstrip().startswith("|")]
        markdown = "\n".join(re.sub(r"-{3,}", "---", line) if SEPARATOR.fullmatch(line) else line for line in lines)
        if not markdown:
            continue
        tables[item.self_ref] = {
            "idx": idx, "markdown": markdown, "caption": item.caption_text(doc),
            "pages": sorted({prov.page_no for prov in item.prov}),
            "regions": regions_of([item], doc.pages),
            # The items a table owns besides itself: read as part of the table, so never as prose too
            "owns": {ref.cref for ref in [*item.captions, *item.footnotes, *item.children]},
        }
    return tables


def prose_of(chunk, tables: dict[str, dict], chunker: HybridChunker, doc: DoclingDocument) -> str:
    """A chunk's text without the tables in it: its headings and its other items, serialized the way
    the chunker serializes one item of a chunk it splits. The chunk's doc_items are plain DocItem copies,
    so each is resolved against the document first to be serialized as what it is.

    ponytail: a paragraph too long for one chunk is split into segments that share the whole paragraph
    as their doc_item, so a segment merged into a chunk with a table gives back the whole paragraph here;
    its rows then come twice and the merge pass has to fold them. Slice the segment out if that bites."""
    owned = set(tables)
    for ref in (d.self_ref for d in chunk.meta.doc_items if d.self_ref in tables):
        owned |= tables[ref]["owns"]
    serializer = chunker.serializer_provider.get_serializer(doc=doc)
    texts = []
    for ref in dict.fromkeys(d.self_ref for d in chunk.meta.doc_items if d.self_ref not in owned):
        item = RefItem(cref=ref).resolve(doc)
        if not isinstance(item, TitleItem | SectionHeaderItem) and (text := serializer.serialize(item=item).text):
            texts.append(text)
    if not texts:
        return ""
    return chunker.contextualize(chunk=chunk.model_copy(update={"text": chunker.delim.join(texts)}))


def convert(
    path: str, on_progress: Callable[[int, int], None] | None = None,
) -> tuple[DoclingDocument, int, list[dict], list[dict]]:
    """Convert a file and return (document, total token count, chunks, tables)."""
    doc = convert_document(path, on_progress)
    tokens = tokenizer().count_tokens(doc.export_to_markdown())
    tables = document_tables(doc)

    chunker = HybridChunker(tokenizer=tokenizer(), merge_peers=True)
    chunks = []
    for idx, chunk in enumerate(chunker.chunk(dl_doc=doc)):
        pages = sorted({prov.page_no for item in chunk.meta.doc_items for prov in item.prov})
        table_refs = list(dict.fromkeys(d.self_ref for d in chunk.meta.doc_items if d.self_ref in tables))
        chunks.append({
            "idx": idx,
            # contextualize() prepends headings, which helps both embedding and answering
            "text": chunker.contextualize(chunk=chunk),
            "pages": pages,
            "headings": chunk.meta.headings or [],
            # Not derived from `pages` above: an independent read of the same provenance, so a
            # doc.pages miss inside regions_of can never change the existing pages/headings behaviour.
            "regions": regions_of(chunk.meta.doc_items, doc.pages),
            "table_refs": [tables[ref]["idx"] for ref in table_refs],
            # Only on a chunk that holds a table: what is left to read once its tables are read whole
            "prose": prose_of(chunk, tables, chunker, doc) if table_refs else None,
        })
    return doc, tokens, chunks, [{k: v for k, v in t.items() if k != "owns"} for t in tables.values()]
