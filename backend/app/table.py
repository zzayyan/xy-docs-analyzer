"""Table Extraction: a user-described table pulled out of every chunk of one document.

Column proposal and the per-chunk read are both structured output over the document's own model
(prior art: app/retrieval/kg.py). Persistence lives in app/store.py, orchestration in app/api.py."""
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel, Field

from app.config import settings
from app.models import llm, table_llm

# A chunk is at most CHUNK_MAX_TOKENS long, so its rows cannot honestly need more output than this.
# The cap is what makes a runaway cost seconds instead of minutes (measured: 7s against 110s).
EXTRACT_MAX_TOKENS = 3000
# Greedy decoding (temperature 0) repeats itself forever on some passages -- measured on Qwen3.5-4B,
# where one chunk ran to 15968 tokens of repeated rows every time. 0.3 still ran away on 3 of 8 retries
# of those chunks, which failed whole runs at random; 0.7 on none of 8 (see docs/adr/0001).
RETRY_TEMPERATURE = 0.7
# The merge pass answers with row numbers only, so its output is small even for a long table.
MERGE_MAX_TOKENS = 2000
# The scope pass answers with part numbers only. Each part is a run of chunks under one heading, shown
# as its heading plus how it begins; past SCOPE_MAX_PARTS the listing no longer fits a small model's
# context, so the whole document is read instead.
# ponytail: all-or-nothing past the cap; scope a long document section by section if that bites.
SCOPE_MAX_TOKENS = 1000
SCOPE_MAX_PARTS = 200
SCOPE_PREVIEW_CHARS = 120
# Two values of one column describe the same thing when they share more than this share of their
# words. Deliberately above one half: "menyerahkan laporan bulanan" and "menyerahkan laporan tahunan"
# share exactly half and are different obligations, so a paraphrase that also shares only half
# ("menyediakan" / "Disediakan tenaga ahli") is left unmerged too (see docs/adr/0002).
SAME_VALUE_OVERLAP = 0.6
WORD = re.compile(r"\w+")

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
    "You extract table rows from one passage of a document, for a request. Return one row per item in "
    "the passage that the request asks for, and no rows at all if the passage has none. Something that "
    "only looks like such an item -- a heading, a menu entry, an example of something else -- is not "
    "one. Give one value per column, in the order the columns are listed. Quote each value exactly as "
    "the passage writes it, in the language of the passage -- do not translate, summarise or infer. "
    "Leave a value empty when the passage does not state it; never fill it with a guess or with words "
    "like \"not stated\"."
)

SCOPE_SYSTEM = (
    "You decide which parts of a document a table has to be read from. You get the request for the "
    "table and the document's parts, numbered, each with its heading and how it begins. Return the "
    "numbers of every part that could state an item the request asks for. Leave out parts that only "
    "mention such items in passing, as examples of something else, or in a list that answers a "
    "different question. When the request asks for every item of its kind anywhere in the document, "
    "or you cannot tell, return every part."
)

MERGE_SYSTEM = (
    "You are given the numbered rows of one table, each pulled out of a different passage of the same "
    "document. Find the rows that describe the same item -- the same obligation, party, date or "
    "amount, mentioned in more than one place -- and return them as groups of row numbers. Only group "
    "rows that are truly one item: two similar but separate items stay apart. Leave out every row "
    "that has no duplicate."
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


class DuplicateGroups(BaseModel):
    groups: list[list[int]] = Field(description="Row numbers that describe the same item, one list per item")


class ScopedParts(BaseModel):
    parts: list[int] = Field(description="Numbers of the parts to read")


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


def chat(model: str | None, **options):
    """The model every table call goes to: TABLE_LLM_MODEL when configured, else the document's own.
    options are llm()'s temperature and max_tokens."""
    if settings.table_llm_model:
        # The output caps above were measured on a model that answers directly. A table model that reasons
        # first spends most of them thinking (Nemotron-3-Super: 2700 tokens on a 500-token chunk), so it
        # gets its own, larger cap instead.
        return table_llm(**{**options, "max_tokens": settings.table_llm_max_tokens})
    return llm(model, **options)


def propose_columns(request: str, model: str | None = None, context: str = "") -> list[dict]:
    """context is the document the columns are for (see document_context); without it the model is
    guessing names from the request's wording alone."""
    described = f"{context}\n\nRequest:\n{request}" if context else request
    proposed = chat(model).with_structured_output(ProposedColumns).invoke([
        ("system", PROPOSE_SYSTEM),
        ("human", described),
    ])
    return [column.model_dump() for column in proposed.columns]


def suggest_tables(context: str, model: str | None = None) -> list[dict]:
    """Tables worth extracting from this document, for a user who has not typed a request yet."""
    suggested = chat(model).with_structured_output(SuggestedTables).invoke([
        ("system", SUGGEST_SYSTEM),
        ("human", context),
    ])
    return [suggestion.model_dump() for suggestion in suggested.tables]


def read_structured(schema: type[BaseModel], messages: list, model: str | None, max_tokens: int) -> BaseModel:
    """Read once greedily, then once more off-greedy if that read runs away (see docs/adr/0001)."""
    try:
        return chat(model, max_tokens=max_tokens).with_structured_output(schema).invoke(messages)
    except Exception:
        return chat(
            model, temperature=RETRY_TEMPERATURE, max_tokens=max_tokens,
        ).with_structured_output(schema).invoke(messages)


def parts_of(chunks: list[dict]) -> list[list[dict]]:
    """Consecutive chunks under the same headings, in document order: the units scope() chooses between."""
    parts: list[list[dict]] = []
    for chunk in chunks:
        if parts and (parts[-1][0].get("headings") or []) == (chunk.get("headings") or []):
            parts[-1].append(chunk)
        else:
            parts.append([chunk])
    return parts


def scope(request: str, chunks: list[dict], model: str | None) -> list[dict]:
    """The chunks a table has to be read from, chosen once with the whole document in view.

    Each chunk is otherwise read on its own, and on its own a passage listing regulations as examples of
    a website's catalogue looks exactly like one listing a law's legal basis (measured on a 46-chunk
    document: 73 rows where 5 answered the request, on a 120B model as on a 4B one). Seeing every part's
    heading side by side is what tells them apart. Anything short of a usable answer -- a failed call, no
    valid part, too many parts to show -- reads the whole document: a table that reads too much is noisy,
    one that reads too little silently misses rows (see docs/adr/0004)."""
    parts = parts_of(chunks)
    if len(parts) < 2 or len(parts) > SCOPE_MAX_PARTS:
        return chunks
    lines = []
    for i, part in enumerate(parts, start=1):
        heading = " / ".join(part[0].get("headings") or []) or "(no heading)"
        opening = " ".join(part[0]["text"].split())
        opening = opening.removeprefix(" ".join(heading.split(" / ")).strip()).strip()
        lines.append(f"{i}. {heading[:CONTEXT_SECTION_CHARS]} -- {opening[:SCOPE_PREVIEW_CHARS]}")
    messages = [("system", SCOPE_SYSTEM), ("human", f"Request:\n{request}\n\nParts:\n" + "\n".join(lines))]
    try:
        chosen = read_structured(ScopedParts, messages, model, SCOPE_MAX_TOKENS).parts
    except Exception:
        return chunks
    picked = {i for i in chosen if 1 <= i <= len(parts)}
    if not picked:
        return chunks
    return [chunk for i, part in enumerate(parts, start=1) if i in picked for chunk in part]


def extract_one(text: str, columns: list[dict], model: str | None, request: str) -> ChunkRows:
    """One LLM call, no database access, so it is safe to run many at once. The off-greedy second read
    is what keeps one awkward passage from costing a whole document its table.

    The request goes in with the columns: the columns alone say what a row looks like, not which items
    belong, so without it every list in the document that fits the columns came back as rows."""
    listed = "\n".join(f"{i}. {c['name']}: {c['description']}" for i, c in enumerate(columns, start=1))
    asked = f"Request:\n{request}\n\n" if request else ""
    messages = [("system", EXTRACT_SYSTEM), ("human", f"{asked}Columns:\n{listed}\n\nPassage:\n{text}")]
    return read_structured(ChunkRows, messages, model, EXTRACT_MAX_TOKENS)


def quoted(value: str, text: str) -> bool:
    """Whether the passage states this value, word for word. Compared as words, ignoring case and
    punctuation, so a quote the model re-spaced or re-punctuated still counts; a value the passage never
    says ("masih berlaku" for a status it does not give, "tidak disebutkan", a list item's number read as
    a document number) does not."""
    words = " ".join(WORD.findall(value.lower()))
    return bool(words) and f" {words} " in f" {' '.join(WORD.findall(text.lower()))} "


def find_duplicates(rows: list[dict], columns: list[dict], model: str | None) -> list[list[int]]:
    """Which rows describe the same item, as groups of row numbers. The model only points at rows;
    merge_rows does the merging, so a cell value is never rewritten -- it stays quoted as written."""
    listed = "\n".join(
        f"{i}. " + " | ".join(f"{c['name']}: {row['values'].get(c['name'], '')}" for c in columns)
        for i, row in enumerate(rows)
    )
    found = read_structured(DuplicateGroups, [("system", MERGE_SYSTEM), ("human", listed)], model, MERGE_MAX_TOKENS)
    return found.groups


def merge_rows(rows: list[dict], groups: list[list[int]]) -> list[dict]:
    """Fold each group of duplicate rows into one, at the place its first member was found.

    The groups come from a model, so they are trusted only as far as they are valid: numbers out of
    range, repeated, or already claimed by an earlier group are dropped, a member that contradicts
    one already in its group stays a row of its own, and a group left with one member merges nothing.
    The contradiction check is the one that matters -- measured on a real document, Qwen3.5-4B
    grouped 90 of 99 rows, nearly all of them different items."""
    claimed: set[int] = set()
    merged_at: dict[int, list[int]] = {}
    for group in groups:
        members: list[int] = []
        for i in dict.fromkeys(group):
            if 0 <= i < len(rows) and i not in claimed and all(same_item(rows[i], rows[m]) for m in members):
                members.append(i)
        if len(members) > 1:
            claimed.update(members)
            merged_at[members[0]] = members

    merged = []
    for i, row in enumerate(rows):
        if i in claimed and i not in merged_at:
            continue  # folded into an earlier row
        merged.append(combine([rows[m] for m in merged_at.get(i, [i])]))
    return merged


def same_item(a: dict, b: dict) -> bool:
    """Two rows can be one item only if no column contradicts: in each, one value is empty, or one's
    words are contained in the other's ("15 Februari 2027" in "paling lambat 15 Februari 2027"), or
    they share most of their words (the same obligation worded two ways). Two items that differ in
    any column -- a name, a deadline -- are two items, whatever the model said."""
    return all(compatible(a["values"].get(name, ""), b["values"].get(name, "")) for name in a["values"])


def compatible(a: str, b: str) -> bool:
    words_a, words_b = set(WORD.findall(a.lower())), set(WORD.findall(b.lower()))
    if not words_a or not words_b or words_a <= words_b or words_b <= words_a:
        return True
    return len(words_a & words_b) / len(words_a | words_b) >= SAME_VALUE_OVERLAP


def combine(duplicates: list[dict]) -> dict:
    """One row from several that describe the same item: each cell takes the first non-empty value
    (one mention may state a deadline another left out), and the row cites every chunk once."""
    names = duplicates[0]["values"].keys()
    values = {name: next((d["values"][name] for d in duplicates if d["values"].get(name)), "") for name in names}
    citations: list[dict] = []
    for citation in (c for d in duplicates for c in d["citations"]):
        if citation["chunk_id"] not in {c["chunk_id"] for c in citations}:
            citations.append({**citation, "n": len(citations) + 1})
    return {"values": values, "citations": citations}


def run(
    chunks: list[dict], columns: list[dict], model: str | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    request: str = "",
) -> list[dict]:
    """Read every chunk and return the rows found, each citing the chunk it came from.

    Rows keep chunk order, and a chunk the model fails on fails the whole run: a partial table would
    silently claim to cover the whole document. should_stop is asked before each chunk's rows are
    taken, and raises Stopped -- that is how a user cancels a run that has minutes left. Items found in
    more than one chunk are merged at the end (merge_rows).

    A value the chunk does not state word for word is blanked (see quoted), and a row left with no
    value at all is dropped: measured on Qwen3.5-4B, a status the passage never gives was filled in on
    nearly every row, and headings came back as rows of blanks."""
    if request:
        chunks = scope(request, chunks, model)
    rows: list[dict] = []
    # One HTTP call per chunk, so it parallelises; map() keeps chunk order however the calls
    # interleave. Closing its iterator (on Stopped, or on a chunk the model failed twice on) cancels
    # every chunk not yet started, so neither cancelling nor failing pays for the rest of the document.
    with ThreadPoolExecutor(max_workers=settings.llm_concurrency) as pool:
        extracted = pool.map(lambda chunk: extract_one(chunk["text"], columns, model, request), chunks)

        for done, (chunk, found) in enumerate(zip(chunks, extracted), start=1):
            if should_stop and should_stop():
                extracted.close()
                raise Stopped()
            citation = {
                "n": 1, "chunk_id": chunk["id"], "pages": chunk["pages"],
                "headings": chunk.get("headings") or [], "regions": chunk.get("regions") or [],
                "source": "table", "text": chunk["text"],
            }
            for row in found.rows:
                # The model can return fewer values than there are columns; a column it skipped is
                # a value the document does not state, which is an empty cell rather than a shift.
                values = [v.strip() if quoted(v, chunk["text"]) else "" for v in row.values] + [""] * len(columns)
                if not any(values[:len(columns)]):
                    continue
                rows.append({
                    "values": {c["name"]: v for c, v in zip(columns, values)},
                    "citations": [dict(citation)],
                })
            if on_progress:
                on_progress(done, len(chunks))

    if len(rows) < 2:
        return rows  # nothing to merge, so no call
    if should_stop and should_stop():
        raise Stopped()
    try:
        # ponytail: one merge call over every row, so a table past roughly the model's context window
        # (a few hundred rows at LLM_NUM_CTX 16384) fails to merge. Merge in batches if that happens.
        groups = find_duplicates(rows, columns, model)
    except Exception:
        # The rows took minutes to read and are all correct, just not deduplicated; a failed merge is
        # no reason to throw them away.
        return rows
    return merge_rows(rows, groups)
