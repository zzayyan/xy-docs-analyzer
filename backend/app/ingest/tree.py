"""PageIndex-style section tree built from Docling headings, with an LLM summary per section."""
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from docling_core.types.doc.document import DoclingDocument, SectionHeaderItem, TitleItem

from app.config import settings
from app.db import graph
from app.models import llm
from app.prompts import ingest as prompts

FALLBACK_GROUP_CHUNKS = 8
SUMMARY_MAX_CHARS = 12000
SUMMARY_ATTEMPTS = 3

LETTER = re.compile(r"^[A-Z][.)]\s+")
NUMBER = re.compile(
    r"^(?:(?:step|langkah|tahap|bab|bagian|chapter|section)\s+)?(\d+(?:\.\d+)*)[.):]?\s+",
    re.IGNORECASE,
)

def headings_from_doc(doc: DoclingDocument) -> list[tuple[int, str]]:
    return [
        (0 if isinstance(item, TitleItem) else item.level, item.text.strip())
        for item, _depth in doc.iterate_items()
        if isinstance(item, (TitleItem, SectionHeaderItem)) and item.text.strip()
    ]


def infer_levels(headings: list[tuple[int, str]]) -> list[int]:
    """Keep Docling levels when they are nested; otherwise derive depth from numbering ("A.", "2", "2.1", "Step 3:")."""
    if len({level for level, _ in headings if level > 0}) > 1:
        return [level for level, _ in headings]

    # ponytail: unnumbered headings nest under the last numbered one, so a trailing unnumbered top-level
    # section gets mis-nested; tree search still sees summaries
    levels, letter_base, last_numbered = [], 0, 0
    for _, title in headings:
        if LETTER.match(title):
            level = letter_base = last_numbered = 1
        elif match := NUMBER.match(title):
            level = last_numbered = letter_base + match.group(1).count(".") + 1
        else:
            level = last_numbered + 1 if last_numbered else 1
        levels.append(level)
    return levels


def normalize(text: str) -> str:
    return " ".join(text.lower().split())


def build_sections(file_id: str, headings: list[tuple[int, str]], chunks: list[dict]) -> tuple[list[dict], dict[str, str]]:
    """(sections in document order, chunk_id -> section_id)."""
    sections: list[dict] = []
    chunk_section: dict[str, str] = {}

    if headings:
        levels = infer_levels(headings)
        stack: list[dict] = []
        for order, ((_, title), level) in enumerate(zip(headings, levels)):
            while stack and stack[-1]["level"] >= level:
                stack.pop()
            section = {
                "id": f"{file_id}:s{order}",
                "order": order,
                "title": title,
                "level": level,
                "parent": stack[-1]["id"] if stack else None,
            }
            sections.append(section)
            stack.append(section)

        # Chunks and headings share document order, so the match only moves forward
        position = 0
        for chunk in chunks:
            if chunk["headings"]:
                target = normalize(chunk["headings"][-1])
                position = next(
                    (i for i in range(position, len(sections)) if normalize(sections[i]["title"]) == target),
                    position,
                )
            chunk_section[chunk["id"]] = sections[position]["id"]
    else:
        for start in range(0, len(chunks), FALLBACK_GROUP_CHUNKS):
            order = len(sections)
            section = {"id": f"{file_id}:s{order}", "order": order, "title": f"Part {order + 1}", "level": 1, "parent": None}
            sections.append(section)
            for chunk in chunks[start:start + FALLBACK_GROUP_CHUNKS]:
                chunk_section[chunk["id"]] = section["id"]

    pages: dict[str, set[int]] = {s["id"]: set() for s in sections}
    for chunk in chunks:
        pages[chunk_section[chunk["id"]]].update(chunk["pages"])
    # Descendants always come after their ancestors, so a reverse pass rolls pages up the tree
    for section in reversed(sections):
        if section["parent"]:
            pages[section["parent"]] |= pages[section["id"]]
    for section in sections:
        section_pages = pages[section["id"]]
        section["start_page"] = min(section_pages) if section_pages else None
        section["end_page"] = max(section_pages) if section_pages else None
    return sections, chunk_section


def summarize_sections(
    sections: list[dict],
    chunks: list[dict],
    chunk_section: dict[str, str],
    on_progress: Callable[[int, int], None] | None = None,
) -> None:
    texts: dict[str, list[str]] = {}
    for chunk in chunks:
        texts.setdefault(chunk_section[chunk["id"]], []).append(chunk["text"])
    child_titles: dict[str, list[str]] = {}
    for section in sections:
        if section["parent"]:
            child_titles.setdefault(section["parent"], []).append(section["title"])

    def summarize(section: dict) -> str:
        if section["id"] not in texts:
            return "Contains: " + "; ".join(child_titles.get(section["id"], []))
        text = "\n\n".join(texts[section["id"]])[:SUMMARY_MAX_CHARS]
        messages = [("system", prompts.SECTION_SUMMARY), ("human", f"Section: {section['title']}\n\n{text}")]
        for _ in range(SUMMARY_ATTEMPTS):
            try:
                return llm().invoke(messages).content.strip()
            except Exception:
                pass
        # The title still guides tree search; one flaky call should not fail the Document
        return section["title"]

    with ThreadPoolExecutor(max_workers=settings.llm_concurrency) as pool:
        summaries = pool.map(summarize, sections)
        try:
            for done, (section, summary) in enumerate(zip(sections, summaries), start=1):
                section["summary"] = summary
                if on_progress:
                    on_progress(done, len(sections))
        finally:
            summaries.close()  # on Deleted, cancels sections not yet started


def store_tree(file_id: str, sections: list[dict], chunk_section: dict[str, str]) -> None:
    graph().query(
        """
        MATCH (f:File {id: $file_id})
        UNWIND $sections AS s
        MERGE (n:Section {id: s.id})
        SET n.file_id = $file_id, n.title = s.title, n.level = s.level, n.order = s.order,
            n.summary = s.summary, n.start_page = s.start_page, n.end_page = s.end_page
        FOREACH (_ IN CASE WHEN s.parent IS NULL THEN [1] ELSE [] END | MERGE (f)-[:HAS_SECTION]->(n))
        """,
        {"file_id": file_id, "sections": sections},
    )
    graph().query(
        """
        UNWIND $sections AS s
        WITH s WHERE s.parent IS NOT NULL
        MATCH (parent:Section {id: s.parent}), (child:Section {id: s.id})
        MERGE (parent)-[:HAS_CHILD]->(child)
        """,
        {"sections": sections},
    )
    graph().query(
        """
        UNWIND $links AS l
        MATCH (c:Chunk {id: l.chunk}), (s:Section {id: l.section})
        MERGE (c)-[:IN_SECTION]->(s)
        """,
        {"links": [{"chunk": chunk_id, "section": section_id} for chunk_id, section_id in chunk_section.items()]},
    )


def build_tree(
    file_id: str,
    doc: DoclingDocument,
    chunks: list[dict],
    on_progress: Callable[[int, int], None] | None = None,
) -> None:
    sections, chunk_section = build_sections(file_id, headings_from_doc(doc), chunks)
    summarize_sections(sections, chunks, chunk_section, on_progress)
    store_tree(file_id, sections, chunk_section)
