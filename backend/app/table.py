"""Table Extraction: a user-described table pulled out of every chunk of one document.

Column proposal and the per-chunk read are both structured output over the document's own model
(prior art: app/retrieval/kg.py). Persistence lives in app/store.py, orchestration in app/api.py."""
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel, Field

from app.config import settings
from app.models import llm

# A chunk is at most CHUNK_MAX_TOKENS long, so its rows cannot honestly need more output than this.
# The cap is what makes a runaway cost seconds instead of minutes (measured: 7s against 110s).
EXTRACT_MAX_TOKENS = 3000
# Greedy decoding (temperature 0) repeats itself forever on some passages -- measured on Qwen3.5-4B,
# where one chunk ran to 15968 tokens of repeated rows every time, and read cleanly off-greedy.
RETRY_TEMPERATURE = 0.3

# How much of the document is shown when proposing columns: enough to pick up its own wording,
# small enough to prepend to a single call. Sections come from the outline, so only long documents
# have them; the opening chunks are what a short document has instead.
CONTEXT_SECTIONS = 40
CONTEXT_SECTION_CHARS = 80
CONTEXT_CHUNKS = 5
CONTEXT_CHUNK_CHARS = 600

PROPOSE_SYSTEM = (
    "You design the columns of a table from a plain-language request. Propose between two and six "
    "columns, each with a short name and a one-sentence description of what belongs in it. Name and "
    "describe the columns in the same language as the request. Where the document quoted below "
    "already has a word for something, use that word. Do not invent columns the request does not ask "
    "for."
)

SUGGEST_SYSTEM = (
    "You propose tables worth pulling out of a document, from an outline and a few passages of it. "
    "Give three tables: things the document lists over and over -- obligations, parties, dates, "
    "amounts, articles -- not a summary of it. Each table has a short title, one plain sentence "
    "asking for what it collects, and between two and six columns, each column with a short name and "
    "a one-sentence description. Write all of it in the language of the document."
)

EXTRACT_SYSTEM = (
    "You extract table rows from one passage of a document. Return one row per item in the passage "
    "that matches the columns, and no rows at all if the passage has none. Give one value per column, "
    "in the order the columns are listed. Quote each value exactly as the passage writes it, in the "
    "language of the passage -- do not translate, summarise or infer. Leave a value empty when the "
    "passage does not state it."
)


class Stopped(Exception):
    """Raised when a run is cancelled mid-way: an outcome the user asked for, not a failure."""


class Column(BaseModel):
    name: str = Field(description="Short column name")
    description: str = Field(default="", description="What belongs in this column")


class ProposedColumns(BaseModel):
    columns: list[Column]


class SuggestedTable(BaseModel):
    title: str = Field(description="Short title for this table")
    request: str = Field(description="What to pull out of the document, in one plain sentence")
    columns: list[Column]


class SuggestedTables(BaseModel):
    tables: list[SuggestedTable]


class ExtractedRow(BaseModel):
    values: list[str] = Field(description="One value per column, in the order the columns are listed")


class ChunkRows(BaseModel):
    rows: list[ExtractedRow]


def document_context(sections: list[dict], chunks: list[dict]) -> str:
    """A short, bounded picture of one document: its outline, then its opening chunks.

    Every part is capped, so a document with hundreds of long headings cannot crowd out the request
    this context is prepended to. Pure text assembly, so the callers holding the Neo4j rows decide
    what to read."""
    parts = []
    if sections:
        titles = "\n".join(f"- {s['title'][:CONTEXT_SECTION_CHARS]}" for s in sections[:CONTEXT_SECTIONS])
        parts.append(f"Outline:\n{titles}")
    if chunks:
        quoted = "\n\n".join(c["text"][:CONTEXT_CHUNK_CHARS] for c in chunks[:CONTEXT_CHUNKS])
        parts.append(f"Passages:\n{quoted}")
    return "\n\n".join(parts)


def propose_columns(request: str, model: str | None = None, context: str = "") -> list[dict]:
    """context is the document the columns are for (see document_context); without it the model is
    guessing names from the request's wording alone."""
    described = f"{context}\n\nRequest:\n{request}" if context else request
    proposed = llm(model).with_structured_output(ProposedColumns).invoke([
        ("system", PROPOSE_SYSTEM),
        ("human", described),
    ])
    return [column.model_dump() for column in proposed.columns]


def suggest_tables(context: str, model: str | None = None) -> list[dict]:
    """Tables worth extracting from this document, for a user who has not typed a request yet."""
    suggested = llm(model).with_structured_output(SuggestedTables).invoke([
        ("system", SUGGEST_SYSTEM),
        ("human", context),
    ])
    return [suggestion.model_dump() for suggestion in suggested.tables]


def extract_one(text: str, columns: list[dict], model: str | None) -> ChunkRows:
    """One LLM call, no database access, so it is safe to run many at once.

    Read once greedily, then once more off-greedy if that read runs away: the second read is what
    keeps one awkward passage from costing a whole document its table (see docs/adr/0001)."""
    listed = "\n".join(f"{i}. {c['name']}: {c['description']}" for i, c in enumerate(columns, start=1))
    messages = [("system", EXTRACT_SYSTEM), ("human", f"Columns:\n{listed}\n\nPassage:\n{text}")]
    try:
        return llm(model, max_tokens=EXTRACT_MAX_TOKENS).with_structured_output(ChunkRows).invoke(messages)
    except Exception:
        return llm(
            model, temperature=RETRY_TEMPERATURE, max_tokens=EXTRACT_MAX_TOKENS,
        ).with_structured_output(ChunkRows).invoke(messages)


def run(
    chunks: list[dict], columns: list[dict], model: str | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> list[dict]:
    """Read every chunk and return the rows found, each citing the chunk it came from.

    Rows keep chunk order, and a chunk the model fails on fails the whole run: a partial table would
    silently claim to cover the whole document. should_stop is asked before each chunk's rows are
    taken, and raises Stopped -- that is how a user cancels a run that has minutes left. Merging items
    found in more than one chunk is a separate ticket, so one item mentioned twice is still two rows
    here."""
    rows: list[dict] = []
    # One HTTP call per chunk, so it parallelises; map() keeps chunk order however the calls
    # interleave. Closing its iterator (on Stopped, or on a chunk the model failed twice on) cancels
    # every chunk not yet started, so neither cancelling nor failing pays for the rest of the document.
    with ThreadPoolExecutor(max_workers=settings.llm_concurrency) as pool:
        extracted = pool.map(lambda chunk: extract_one(chunk["text"], columns, model), chunks)

        for done, (chunk, found) in enumerate(zip(chunks, extracted), start=1):
            if should_stop and should_stop():
                extracted.close()
                raise Stopped()
            citation = {
                "n": 1, "chunk_id": chunk["id"], "pages": chunk["pages"],
                "headings": chunk.get("headings") or [], "source": "table", "text": chunk["text"],
            }
            for row in found.rows:
                # The model can return fewer values than there are columns; a column it skipped is
                # a value the document does not state, which is an empty cell rather than a shift.
                values = [v.strip() for v in row.values] + [""] * len(columns)
                rows.append({
                    "values": {c["name"]: v for c, v in zip(columns, values)},
                    "citations": [dict(citation)],
                })
            if on_progress:
                on_progress(done, len(chunks))
    return rows
