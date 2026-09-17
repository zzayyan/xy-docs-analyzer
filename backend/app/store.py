"""Read and delete Cypher for File/Section/Chunk/Turn/TableExtraction, kept out of app/api.py so routing and queries
don't tangle. Writes made during ingest stay in app/ingest/pipeline.py, app/ingest/tree.py, app/ingest/kg.py."""
import json
import uuid

from app.db import graph

LIST_FILES = """
MATCH (f:File)
RETURN f {.*} AS file
ORDER BY coalesce(f.created_at, 0) DESC
"""

GET_FILE = "MATCH (f:File {id: $id}) RETURN f {.*} AS file"

# Every deletion below is scoped by the file_id property, not by traversal, so execution order does not
# matter and a document deleted mid-ingest cannot leave orphaned nodes behind. Meta is never touched: it
# is global (the active embedding model marker), not per-document.
DELETE_FILE_CASCADE = [
    "MATCH (n:Chunk {file_id: $id}) DETACH DELETE n",
    "MATCH (n:Section {file_id: $id}) DETACH DELETE n",
    "MATCH (n:__Entity__ {file_id: $id}) DETACH DELETE n",
    "MATCH (n:Turn {file_id: $id}) DETACH DELETE n",
    "MATCH (n:TableExtraction {file_id: $id}) DETACH DELETE n",
    "MATCH (f:File {id: $id}) DETACH DELETE f",
]

LIST_SECTIONS = """
MATCH (s:Section {file_id: $file_id})
OPTIONAL MATCH (parent:Section)-[:HAS_CHILD]->(s)
RETURN s.id AS id, s.title AS title, s.level AS level, s.order AS order, s.summary AS summary,
       s.start_page AS start_page, s.end_page AS end_page, parent.id AS parent_id,
       COUNT { (s)<-[:IN_SECTION]-(:Chunk) } AS chunks
ORDER BY s.order
"""

SECTION_CHUNKS = """
MATCH (c:Chunk {file_id: $file_id})-[:IN_SECTION]->(:Section {id: $section_id, file_id: $file_id})
RETURN c.id AS id, c.idx AS idx, c.text AS text, c.pages AS pages, c.headings AS headings
ORDER BY c.idx
"""

ALL_CHUNKS = """
MATCH (c:Chunk {file_id: $file_id})
RETURN c.id AS id, c.text AS text, c.pages AS pages, c.headings AS headings
ORDER BY c.idx
"""

# Columns and rows are JSON-encoded for the same reason citations are: a Neo4j property cannot hold
# a list of maps.
CREATE_TABLE_EXTRACTION = """
MATCH (f:File {id: $file_id})
CREATE (f)-[:HAS_TABLE]->(:TableExtraction {
    id: $id, file_id: $file_id, request: $request, columns: $columns, rows: '[]',
    status: 'queued', progress: 0.0, created_at: timestamp(), updated_at: timestamp()
})
"""

SET_TABLE_EXTRACTION = "MATCH (e:TableExtraction {id: $id}) SET e += $props, e.updated_at = timestamp()"

# Rows are left out on purpose: the list is a history sidebar, and a document's rows can run to
# thousands of chunk quotes each. Open one to get its rows, through GET_TABLE_EXTRACTION.
LIST_TABLE_EXTRACTIONS = """
MATCH (e:TableExtraction {file_id: $file_id})
RETURN e {.id, .request, .columns, .status, .progress, .error, .created_at, .updated_at} AS extraction
ORDER BY e.created_at DESC
"""

GET_TABLE_EXTRACTION = "MATCH (e:TableExtraction {id: $id, file_id: $file_id}) RETURN e {.*} AS extraction"

LIST_TURNS = """
MATCH (t:Turn {file_id: $file_id})
RETURN t.id AS id, t.question AS question, t.answer AS answer, t.citations AS citations,
       t.mode AS mode, t.complete AS complete, t.created_at AS created_at
ORDER BY t.created_at
"""

SAVE_TURN = """
MATCH (f:File {id: $file_id})
CREATE (f)-[:HAS_TURN]->(:Turn {
    id: $id, file_id: $file_id, question: $question, answer: $answer,
    citations: $citations, mode: $mode, complete: $complete, created_at: timestamp()
})
"""

CLEAR_TURNS = "MATCH (t:Turn {file_id: $file_id}) DETACH DELETE t"


def list_files() -> list[dict]:
    return [row["file"] for row in graph().query(LIST_FILES)]


def get_file(file_id: str) -> dict | None:
    rows = graph().query(GET_FILE, {"id": file_id})
    return rows[0]["file"] if rows else None


def delete_file(file_id: str) -> None:
    for statement in DELETE_FILE_CASCADE:
        graph().query(statement, {"id": file_id})


def list_sections(file_id: str) -> list[dict]:
    return graph().query(LIST_SECTIONS, {"file_id": file_id})


def section_chunks(file_id: str, section_id: str) -> list[dict]:
    return graph().query(SECTION_CHUNKS, {"file_id": file_id, "section_id": section_id})


def list_turns(file_id: str) -> list[dict]:
    turns = graph().query(LIST_TURNS, {"file_id": file_id})
    for turn in turns:
        turn["citations"] = json.loads(turn["citations"])
    return turns


def save_turn(
    file_id: str, *, question: str, answer: str, citations: list[dict], mode: str, complete: bool,
    turn_id: str | None = None,
) -> dict:
    """Anchored on MATCH (f:File ...): if the document was deleted mid-answer this is a silent no-op
    rather than an orphaned Turn. Citations are JSON-encoded because Neo4j properties cannot hold a
    list of maps, and are stored denormalised (including chunk text) so history survives re-ingestion
    or a chunk being deleted later.

    turn_id can be supplied by the caller (the streaming endpoint mints it up front so it can be
    sent in the SSE "done" event, before the turn is actually written in a finally block)."""
    turn_id = turn_id or str(uuid.uuid4())
    graph().query(SAVE_TURN, {
        "id": turn_id, "file_id": file_id, "question": question, "answer": answer,
        "citations": json.dumps(citations), "mode": mode, "complete": complete,
    })
    return {
        "id": turn_id, "question": question, "answer": answer, "citations": citations,
        "mode": mode, "complete": complete,
    }


def clear_turns(file_id: str) -> None:
    graph().query(CLEAR_TURNS, {"file_id": file_id})


def list_chunks(file_id: str) -> list[dict]:
    return graph().query(ALL_CHUNKS, {"file_id": file_id})


def _table_extraction(row: dict) -> dict:
    return {**row, "columns": json.loads(row["columns"]), "rows": json.loads(row.get("rows") or "[]")}


def create_table_extraction(file_id: str, request: str, columns: list[dict]) -> dict:
    """Anchored on MATCH (f:File ...), so a document deleted first leaves no orphaned TableExtraction."""
    extraction_id = str(uuid.uuid4())
    graph().query(CREATE_TABLE_EXTRACTION, {
        "id": extraction_id, "file_id": file_id, "request": request, "columns": json.dumps(columns),
    })
    return get_table_extraction(file_id, extraction_id)


def set_table_extraction(extraction_id: str, **props) -> None:
    if "rows" in props:
        props["rows"] = json.dumps(props["rows"])
    graph().query(SET_TABLE_EXTRACTION, {"id": extraction_id, "props": props})


def list_table_extractions(file_id: str) -> list[dict]:
    rows = graph().query(LIST_TABLE_EXTRACTIONS, {"file_id": file_id})
    return [_table_extraction(row["extraction"]) for row in rows]


def get_table_extraction(file_id: str, extraction_id: str) -> dict | None:
    rows = graph().query(GET_TABLE_EXTRACTION, {"id": extraction_id, "file_id": file_id})
    return _table_extraction(rows[0]["extraction"]) if rows else None
