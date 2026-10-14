from pydantic import BaseModel, Field

from app.db import graph
from app.models import llm

MAX_SECTIONS = 3

SECTIONS_QUERY = """
MATCH (s:Section {file_id: $file_id})
RETURN s.id AS id, s.title AS title, s.level AS level, s.summary AS summary,
       s.start_page AS start_page, s.end_page AS end_page
ORDER BY s.order
"""

# A chosen section brings its whole subtree; best-ranked section first, document order inside
CHUNKS_QUERY = """
UNWIND range(0, size($section_ids) - 1) AS rank
MATCH (s:Section {id: $section_ids[rank]})-[:HAS_CHILD*0..]->(:Section)<-[:IN_SECTION]-(c:Chunk)
WITH c, min(rank) AS rank
RETURN c.id AS id, c.text AS text, c.pages AS pages, c.headings AS headings, c.regions AS regions
ORDER BY rank, c.idx
LIMIT $limit
"""

SYSTEM_PROMPT = (
    "You navigate a document outline to find where questions are answered. "
    f"Return up to {MAX_SECTIONS} section ids (the value in square brackets) for each question, most "
    "relevant first. "
    "Prefer the most specific section; choose a parent only when the answer spans its children."
)


class SectionChoice(BaseModel):
    section_ids: list[str] = Field(description="Section ids from the outline, most relevant first")


def outline_line(section: dict) -> str:
    short_id = section["id"].rsplit(":", 1)[-1]
    pages = f" (p. {section['start_page']}-{section['end_page']})" if section["start_page"] else ""
    return f"{'  ' * max(section['level'] - 1, 0)}[{short_id}] {section['title']}{pages}: {section['summary']}"


def search(file_id: str, question: str, limit: int = 12, model: str | None = None) -> list[dict]:
    """The LLM picks sections from the outline. question may hold several questions, one per line."""
    questions = [q for q in question.splitlines() if q.strip()] or [question]
    sections = graph().query(SECTIONS_QUERY, {"file_id": file_id})
    if not sections:
        return []

    # ponytail: whole outline in one prompt; for huge trees show levels <= 2 first, then drill down
    outline = "\n".join(outline_line(s) for s in sections)
    choice = llm(model).with_structured_output(SectionChoice).invoke([
        ("system", SYSTEM_PROMPT),
        ("human", f"Outline:\n{outline}\n\nQuestions:\n" + "\n".join(f"- {q}" for q in questions)),
    ])

    valid_ids = {s["id"] for s in sections}
    section_ids = [f"{file_id}:{sid.strip('[] ')}" for sid in choice.section_ids]
    section_ids = [sid for sid in dict.fromkeys(section_ids) if sid in valid_ids][: MAX_SECTIONS * len(questions)]
    if not section_ids:
        return []
    return graph().query(CHUNKS_QUERY, {"section_ids": section_ids, "limit": limit})
