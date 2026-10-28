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
from docling_core.types.doc.document import DoclingDocument, GroupItem, PageItem, RefItem, TableItem, TextItem
from docling_core.types.doc.labels import DocItemLabel, GroupLabel
from transformers import AutoTokenizer

from app.config import settings

PDF_BATCH_PAGES = 25
TEXT_LAYER_CHARS = 100

# Docling reads more formats; these are the ones the app accepts and tests
SUPPORTED_FORMATS = {
    ".pdf": InputFormat.PDF,
    ".docx": InputFormat.DOCX,
    ".pptx": InputFormat.PPTX,
    ".xlsx": InputFormat.XLSX,
    ".csv": InputFormat.CSV,
    ".html": InputFormat.HTML,
    ".htm": InputFormat.HTML,
    ".md": InputFormat.MD,
    ".png": InputFormat.IMAGE,
    ".jpg": InputFormat.IMAGE,
    ".jpeg": InputFormat.IMAGE,
}


def converted_path(doc_id: str) -> Path:
    """The DoclingDocument kept as JSON, so a viewer can show it without converting again."""
    return settings.data_dir / "docling" / f"{doc_id}.json"


@lru_cache
def converter(ocr: bool = True) -> DocumentConverter:
    options = PdfPipelineOptions(do_ocr=ocr)
    return DocumentConverter(
        allowed_formats=list(set(SUPPORTED_FORMATS.values())),
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)},
    )


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


def cited_rows(table: TableItem, text: str) -> list[int]:
    """Grid rows whose "row, column = value" triplets, as the chunker writes them, are in the chunk's text."""
    # ponytail: assumes one header row; a table with more matches nothing and is cited whole. A row whose
    # triplet a long table's chunk boundary cuts in two is in neither chunk.
    grid = [[cell.text.strip() for cell in row] for row in table.data.grid]
    if not grid:
        return []
    header = grid[0]

    def triplets(row: list[str]) -> list[str]:
        if len(row) == 1:
            return [f"{header[0]} = {row[0]}"]
        return [f"{row[0]}, {header[j]} = {row[j]}" for j in range(1, len(row))]

    return [i for i, row in enumerate(grid[1:], start=1) if any(t in text for t in triplets(row))]


def refs_of(doc_items, text: str, doc: DoclingDocument) -> list[str]:
    """The Docling items a chunk came from, a table narrowed to "{ref}/rows/{n}" for the rows it holds."""
    refs = []
    for item in doc_items:
        # A chunk's items are plain DocItems; the table's grid is only on the document's own item
        table = RefItem(cref=item.self_ref).resolve(doc)
        rows = cited_rows(table, text) if isinstance(table, TableItem) else []
        refs += [f"{item.self_ref}/rows/{row}" for row in rows] or [item.self_ref]
    return refs


def view_blocks(path: Path) -> list[dict]:
    """A kept document's body in reading order as plain-text blocks, each keyed by the ref a citation carries."""
    doc = DoclingDocument.load_from_json(path)
    blocks = []
    for item, _ in doc.iterate_items(with_groups=True):
        page = item.prov[0].page_no if getattr(item, "prov", None) else None
        block = {"ref": item.self_ref, "page": page, "level": 0, "text": "", "rows": []}
        if isinstance(item, GroupItem) and item.label == GroupLabel.SHEET:
            blocks.append({**block, "type": "heading", "level": 2, "text": item.name})
        elif isinstance(item, TableItem):
            blocks.append({**block, "type": "table", "rows": [[cell.text for cell in row] for row in item.data.grid]})
        elif isinstance(item, TextItem):
            if item.label == DocItemLabel.TITLE:
                blocks.append({**block, "type": "heading", "level": 1, "text": item.text})
            elif item.label == DocItemLabel.SECTION_HEADER:
                blocks.append({**block, "type": "heading", "level": item.level + 1, "text": item.text})
            elif item.label == DocItemLabel.LIST_ITEM:
                blocks.append({**block, "type": "list_item", "text": item.text})
            else:
                blocks.append({**block, "type": "paragraph", "text": item.text})
    return blocks


def sheet_tables(path: Path) -> list[tuple[str, str, list[list[str]]]]:
    """A kept document's tables as (name, ref, grid): the sheet's name, numbered when a sheet holds several."""
    tables, sheet = [], None
    for item, _ in DoclingDocument.load_from_json(path).iterate_items(with_groups=True):
        if isinstance(item, GroupItem) and item.label == GroupLabel.SHEET:
            sheet = item.name
        elif isinstance(item, TableItem) and item.data.grid:
            name = sheet or "Table"
            taken = {t[0] for t in tables}
            if name in taken or not sheet:
                name = next(f"{name} {n}" for n in range(2 if sheet else 1, len(tables) + 3) if f"{name} {n}" not in taken)
            tables.append((name, item.self_ref, [[cell.text for cell in row] for row in item.data.grid]))
    return tables


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
            "refs": refs_of(chunk.meta.doc_items, chunk.text, doc),
        })
    return doc, tokens, chunks
