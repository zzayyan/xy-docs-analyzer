"""Table Extraction: a user-described table pulled out of one document's chunks."""
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel, Field

from app.config import settings
from app.models import llm, table_llm
from app.prompts import table as prompts

# Caps a runaway repeat loop at seconds instead of minutes (measured: 7s against 110s)
EXTRACT_MAX_TOKENS = 3000
TABLE_BATCH_ROWS = 40
# ponytail: double EXTRACT_MAX_TOKENS, not measured; size it from a real batch if a long table runs out
TABLE_EXTRACT_MAX_TOKENS = 2 * EXTRACT_MAX_TOKENS
# Greedy decoding loops forever on some passages; 0.3 still looped on 3 of 8 retries, 0.7 on none (docs/adr/0001)
RETRY_TEMPERATURE = 0.7
MERGE_MAX_TOKENS = 2000
# ponytail: past SCOPE_MAX_PARTS the whole document is read; scope section by section if that bites
SCOPE_MAX_TOKENS = 1000
SCOPE_MAX_PARTS = 200
SCOPE_PREVIEW_CHARS = 120
# Above one half on purpose: "laporan bulanan" vs "laporan tahunan" share half and differ (docs/adr/0002)
SAME_VALUE_OVERLAP = 0.6
WORD = re.compile(r"\w+")

CONTEXT_SECTIONS = 40
CONTEXT_SECTION_CHARS = 80
CONTEXT_CHUNKS = 5
CONTEXT_CHUNK_CHARS = 600


class Stopped(Exception):
    """The user cancelled the run."""


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
    """Outline then opening chunks, every part capped so it cannot crowd out the request."""
    parts = []
    if sections:
        titles = "\n".join(f"- {s['title'][:CONTEXT_SECTION_CHARS]}" for s in sections[:CONTEXT_SECTIONS])
        parts.append(f"Outline:\n{titles}")
    if chunks:
        quoted = "\n\n".join(c["text"][:CONTEXT_CHUNK_CHARS] for c in chunks[:CONTEXT_CHUNKS])
        parts.append(f"Passages:\n{quoted}")
    return "\n\n".join(parts)


def chat(model: str | None, **options):
    """TABLE_LLM_MODEL when configured, else the document's own model."""
    if settings.table_llm_model:
        # The caps above assume a model that answers directly; a reasoning model spends them thinking
        return table_llm(**{**options, "max_tokens": settings.table_llm_max_tokens})
    return llm(model, **options)


def propose_columns(request: str, model: str | None = None, context: str = "") -> list[dict]:
    described = f"{context}\n\nRequest:\n{request}" if context else request
    proposed = chat(model).with_structured_output(ProposedColumns).invoke([
        ("system", prompts.PROPOSE),
        ("human", described),
    ])
    return [column.model_dump() for column in proposed.columns]


def suggest_tables(context: str, model: str | None = None) -> list[dict]:
    suggested = chat(model).with_structured_output(SuggestedTables).invoke([
        ("system", prompts.SUGGEST),
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
    """Consecutive chunks under the same headings."""
    parts: list[list[dict]] = []
    for chunk in chunks:
        if parts and (parts[-1][0].get("headings") or []) == (chunk.get("headings") or []):
            parts[-1].append(chunk)
        else:
            parts.append([chunk])
    return parts


def part_titles(chunks: list[dict]) -> list[str]:
    return [" / ".join(part[0].get("headings") or []) or "-" for part in parts_of(chunks)]


def scope(request: str, chunks: list[dict], model: str | None) -> list[dict]:
    """The chunks worth reading, chosen with every part's heading in view (docs/adr/0004). Any doubt
    reads the whole document: too much is noisy, too little silently misses rows."""
    parts = parts_of(chunks)
    if len(parts) < 2 or len(parts) > SCOPE_MAX_PARTS:
        return chunks
    lines = []
    for i, part in enumerate(parts, start=1):
        heading = " / ".join(part[0].get("headings") or []) or "(no heading)"
        opening = " ".join(part[0]["text"].split())
        opening = opening.removeprefix(" ".join(heading.split(" / ")).strip()).strip()
        # A table's heading may say nothing about it, so its caption is shown too
        captions = dict.fromkeys(t["caption"][:CONTEXT_SECTION_CHARS] for c in part for t in c.get("tables") or [] if t.get("caption"))
        tables = f" [tables: {'; '.join(captions)}]" if captions else ""
        lines.append(f"{i}. {heading[:CONTEXT_SECTION_CHARS]} -- {opening[:SCOPE_PREVIEW_CHARS]}{tables}")
    messages = [("system", prompts.SCOPE), ("human", f"Request:\n{request}\n\nParts:\n" + "\n".join(lines))]
    try:
        chosen = read_structured(ScopedParts, messages, model, SCOPE_MAX_TOKENS).parts
    except Exception:
        return chunks
    picked = {i for i in chosen if 1 <= i <= len(parts)}
    if not picked:
        return chunks
    return [chunk for i, part in enumerate(parts, start=1) if i in picked for chunk in part]


def extract_one(text: str, columns: list[dict], model: str | None, request: str) -> ChunkRows:
    # The request goes in too: columns alone made every list that fits them come back as rows
    listed = "\n".join(f"{i}. {c['name']}: {c['description']}" for i, c in enumerate(columns, start=1))
    asked = f"Request:\n{request}\n\n" if request else ""
    messages = [("system", prompts.EXTRACT), ("human", f"{asked}Columns:\n{listed}\n\nPassage:\n{text}")]
    return read_structured(ChunkRows, messages, model, EXTRACT_MAX_TOKENS)


def extract_from_table(text: str, columns: list[dict], model: str | None, request: str) -> ChunkRows:
    listed = "\n".join(f"{i}. {c['name']}: {c['description']}" for i, c in enumerate(columns, start=1))
    asked = f"Request:\n{request}\n\n" if request else ""
    messages = [("system", prompts.EXTRACT_TABLE), ("human", f"{asked}Columns:\n{listed}\n\nTable:\n{text}")]
    return read_structured(ChunkRows, messages, model, TABLE_EXTRACT_MAX_TOKENS)


def table_batches(table: dict) -> list[str]:
    """Runs of TABLE_BATCH_ROWS rows, each under the table's caption and header."""
    lines = table["markdown"].splitlines()
    header, body = lines[:2], lines[2:]
    caption = f"{table['caption']}\n\n" if table.get("caption") else ""
    starts = range(0, len(body), TABLE_BATCH_ROWS) if body else [0]
    return [caption + "\n".join(header + body[i:i + TABLE_BATCH_ROWS]) for i in starts]


def units_of(chunks: list[dict]) -> list[dict]:
    """What run() reads, in order: each table once, whole, at its first chunk, then each chunk's text.
    A chunk holding a table contributes only its prose, so the table's rows are not read twice."""
    units: list[dict] = []
    seen: set[str] = set()
    for position, chunk in enumerate(chunks):
        tables = chunk.get("tables") or []
        for table in tables:
            if table["id"] in seen:
                continue
            seen.add(table["id"])
            for text in table_batches(table):
                units.append({"text": text, "table": True, "chunk": position, "citation": {
                    "chunk_id": chunk["id"], "pages": table["pages"], "headings": chunk.get("headings") or [],
                    "regions": table["regions"],
                }})
        text = (chunk.get("prose") or "") if tables else chunk["text"]
        if text:
            units.append({"text": text, "table": False, "chunk": position, "citation": {
                "chunk_id": chunk["id"], "pages": chunk["pages"], "headings": chunk.get("headings") or [],
                "regions": chunk.get("regions") or [],
            }})
    return units


def quoted(value: str, text: str) -> bool:
    """Whether the passage states this value word for word, ignoring case, spacing and punctuation."""
    words = " ".join(WORD.findall(value.lower()))
    return bool(words) and f" {words} " in f" {' '.join(WORD.findall(text.lower()))} "


def find_duplicates(rows: list[dict], columns: list[dict], model: str | None) -> list[list[int]]:
    # The model only points at rows; merge_rows merges, so no cell value is ever rewritten
    listed = "\n".join(
        f"{i}. " + " | ".join(f"{c['name']}: {row['values'].get(c['name'], '')}" for c in columns)
        for i, row in enumerate(rows)
    )
    found = read_structured(DuplicateGroups, [("system", prompts.MERGE), ("human", listed)], model, MERGE_MAX_TOKENS)
    return found.groups


def merge_rows(rows: list[dict], groups: list[list[int]]) -> list[dict]:
    """Fold each group into one row at its first member's place. Groups come from a model, so invalid
    numbers are dropped and a member that contradicts its group stays apart (a 4B model grouped 90 of
    99 rows, nearly all different items)."""
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
            continue
        merged.append(combine([rows[m] for m in merged_at.get(i, [i])]))
    return merged


def same_item(a: dict, b: dict) -> bool:
    """One item only if no column contradicts: per column, one value is empty, contains the other, or
    shares most of its words."""
    return all(compatible(a["values"].get(name, ""), b["values"].get(name, "")) for name in a["values"])


def compatible(a: str, b: str) -> bool:
    words_a, words_b = set(WORD.findall(a.lower())), set(WORD.findall(b.lower()))
    if not words_a or not words_b or words_a <= words_b or words_b <= words_a:
        return True
    return len(words_a & words_b) / len(words_a | words_b) >= SAME_VALUE_OVERLAP


def combine(duplicates: list[dict]) -> dict:
    """Each cell takes the first non-empty value; the row cites every chunk once."""
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
    """Rows found in the chunks, each citing its source, duplicates merged at the end.

    A failed read fails the whole run: a partial table would silently claim to cover the document.
    Values not quoted word for word are blanked and all-blank rows dropped, since small models invent
    values and return headings as rows."""
    units = units_of(chunks)
    rows: list[dict] = []
    # Leaving the block on Stopped or failure cancels every unit not yet started
    with ThreadPoolExecutor(max_workers=settings.llm_concurrency) as pool:
        extracted = pool.map(
            lambda unit: (extract_from_table if unit["table"] else extract_one)(unit["text"], columns, model, request),
            units,
        )

        for i, (unit, found) in enumerate(zip(units, extracted)):
            if should_stop and should_stop():
                extracted.close()
                raise Stopped()
            citation = {"n": 1, **unit["citation"], "source": "table", "text": unit["text"]}
            for row in found.rows:
                # Padded: a model returning fewer values than columns leaves cells empty
                values = [v.strip() if quoted(v, unit["text"]) else "" for v in row.values] + [""] * len(columns)
                if not any(values[:len(columns)]):
                    continue
                rows.append({
                    "values": {c["name"]: v for c, v in zip(columns, values)},
                    "citations": [dict(citation)],
                })
            done = units[i + 1]["chunk"] if i + 1 < len(units) else len(chunks)
            if on_progress and done > unit["chunk"]:
                on_progress(done, len(chunks))

    if len(rows) < 2:
        return rows
    if should_stop and should_stop():
        raise Stopped()
    try:
        # ponytail: one merge call over every row, fails past the context window; merge in batches if it bites
        groups = find_duplicates(rows, columns, model)
    except Exception:
        # Unmerged rows are still correct rows
        return rows
    return merge_rows(rows, groups)
