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

# The File goes first: every write that creates nodes is anchored on MATCH (f:File) or on a Chunk deleted
# further down, so once the File is gone an ingest still running writes nothing new, and the statements
# after it (scoped by file_id, not traversal) sweep whatever it wrote before. File last would leave a
# window where chunks written between the Chunk and File statements survive, orphaned. Meta is never
# touched: it is global (the active embedding model marker), not per-document.
DELETE_FILE_CASCADE = [
    "MATCH (f:File {id: $id}) DETACH DELETE f",
    "MATCH (n:Chunk {file_id: $id}) DETACH DELETE n",
    "MATCH (n:Section {file_id: $id}) DETACH DELETE n",
    "MATCH (n:__Entity__ {file_id: $id}) DETACH DELETE n",
    "MATCH (n:Turn {file_id: $id}) DETACH DELETE n",
    "MATCH (n:TableExtraction {file_id: $id}) DETACH DELETE n",
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
RETURN c.id AS id, c.text AS text, c.pages AS pages, c.headings AS headings, c.regions AS regions
ORDER BY c.idx
"""

# Same rows as ALL_CHUNKS, but for callers that only need the opening of the document (proposing
# columns), so a 200-page document is not read in full for a single prompt.
FIRST_CHUNKS = ALL_CHUNKS + "LIMIT $limit"

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

# A run's own final write: a cancel that landed while the run was merging rows stays cancelled
FINISH_TABLE_EXTRACTION = """
MATCH (e:TableExtraction {id: $id}) WHERE e.status = 'running'
SET e += $props, e.updated_at = timestamp()
"""

# Rows are left out on purpose: the list is a history sidebar, and a document's rows can run to
# thousands of chunk quotes each. Open one to get its rows, through GET_TABLE_EXTRACTION.
LIST_TABLE_EXTRACTIONS = """
MATCH (e:TableExtraction {file_id: $file_id})
RETURN e {.id, .request, .columns, .status, .progress, .error, .chunks_done, .chunks_total,
          .created_at, .updated_at} AS extraction
ORDER BY e.created_at DESC
"""

GET_TABLE_EXTRACTION = "MATCH (e:TableExtraction {id: $id, file_id: $file_id}) RETURN e {.*} AS extraction"

DELETE_TABLE_EXTRACTION = "MATCH (e:TableExtraction {id: $id, file_id: $file_id}) DETACH DELETE e"

LIST_TURNS = """
MATCH (t:Turn {file_id: $file_id})
RETURN t.id AS id, t.question AS question, t.answer AS answer, t.citations AS citations,
       t.mode AS mode, t.complete AS complete, t.created_at AS created_at
ORDER BY t.created_at
"""

# What a new question needs of the conversation so far: the latest complete turns, text only -- not every
# Turn with its citations (chunk text included) re-read and decoded on every question.
RECENT_TURNS = """
MATCH (t:Turn {file_id: $file_id}) WHERE t.complete
WITH t ORDER BY t.created_at DESC LIMIT $n
RETURN t.question AS question, t.answer AS answer
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


FAIL_INTERRUPTED = [
    "MATCH (f:File) WHERE NOT f.status IN ['done', 'error'] SET f.status = 'error', f.error = $error, f.updated_at = timestamp()",
    "MATCH (e:TableExtraction) WHERE e.status IN ['queued', 'running'] "
    "SET e.status = 'error', e.error = $error, e.updated_at = timestamp()",
]


def fail_interrupted(error: str) -> None:
    """Marks every unfinished ingest and Table Extraction as failed. Only right at startup, before any
    background task of this process has begun: nothing else can be running then."""
    for statement in FAIL_INTERRUPTED:
        graph().query(statement, {"error": error})


# The knowledge graph as the Graph tab draws it: the most mentioned entities, and only the relationships
# between two of them, so no edge points at a node that is not drawn.
GRAPH_TOP = """
MATCH (e:__Entity__ {file_id: $file_id})
WITH e, COUNT { (:Chunk)-[:MENTIONS]->(e) } AS mentions
ORDER BY mentions DESC, e.key
LIMIT $limit
WITH collect(e) AS top, collect({key: e.key, name: e.name, type: e.type, mentions: mentions}) AS nodes
UNWIND top AS a
OPTIONAL MATCH (a)-[r]->(b:__Entity__) WHERE b IN top AND b <> a
WITH nodes, collect(CASE WHEN r IS NULL THEN null ELSE {source: a.key, target: b.key, type: type(r)} END) AS edges
RETURN nodes, edges, COUNT { (:__Entity__ {file_id: $file_id}) } AS total
"""

ENTITY = """
MATCH (e:__Entity__ {file_id: $file_id, key: $key})
RETURN e.key AS key, e.name AS name, e.type AS type, COUNT { (:Chunk)-[:MENTIONS]->(e) } AS mentions
"""

# One step out from an entity, both directions, most mentioned neighbours first
ENTITY_NEIGHBOURS = """
MATCH (e:__Entity__ {file_id: $file_id, key: $key})-[r]-(n:__Entity__)
WHERE n <> e
WITH r, n, startNode(r) = e AS outgoing, COUNT { (:Chunk)-[:MENTIONS]->(n) } AS mentions
ORDER BY mentions DESC, n.key
LIMIT $limit
RETURN n.key AS key, n.name AS name, n.type AS type, mentions, type(r) AS rel, outgoing
"""

ENTITY_CHUNKS = """
MATCH (c:Chunk {file_id: $file_id})-[:MENTIONS]->(:__Entity__ {file_id: $file_id, key: $key})
RETURN c.id AS id, c.text AS text, c.pages AS pages, c.headings AS headings, c.regions AS regions
ORDER BY c.idx
LIMIT $limit
"""


def graph_top(file_id: str, limit: int) -> dict:
    [row] = graph().query(GRAPH_TOP, {"file_id": file_id, "limit": limit}) or [{"nodes": [], "edges": [], "total": 0}]
    return {"nodes": row["nodes"], "edges": [e for e in row["edges"] if e], "total": row["total"]}


def entity(file_id: str, key: str) -> dict | None:
    rows = graph().query(ENTITY, {"file_id": file_id, "key": key})
    return rows[0] if rows else None


def entity_neighbours(file_id: str, key: str, limit: int) -> list[dict]:
    return graph().query(ENTITY_NEIGHBOURS, {"file_id": file_id, "key": key, "limit": limit})


def entity_chunks(file_id: str, key: str, limit: int) -> list[dict]:
    rows = graph().query(ENTITY_CHUNKS, {"file_id": file_id, "key": key, "limit": limit})
    return [{**row, "regions": json.loads(row.get("regions") or "[]")} for row in rows]


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


def recent_turns(file_id: str, n: int) -> list[dict]:
    """The last n complete turns, oldest first, as {question, answer}."""
    return graph().query(RECENT_TURNS, {"file_id": file_id, "n": n})


def save_turn(
    file_id: str, *, question: str, answer: str, citations: list[dict], mode: str, complete: bool,
    turn_id: str,
) -> None:
    """Anchored on MATCH (f:File ...): if the document was deleted mid-answer this is a silent no-op
    rather than an orphaned Turn. Citations are JSON-encoded because Neo4j properties cannot hold a
    list of maps, and are stored denormalised (including chunk text) so history survives re-ingestion
    or a chunk being deleted later. turn_id is minted by the streaming endpoint, which sends it in the
    SSE "done" event."""
    graph().query(SAVE_TURN, {
        "id": turn_id, "file_id": file_id, "question": question, "answer": answer,
        "citations": json.dumps(citations), "mode": mode, "complete": complete,
    })


def clear_turns(file_id: str) -> None:
    graph().query(CLEAR_TURNS, {"file_id": file_id})


def list_chunks(file_id: str, limit: int | None = None) -> list[dict]:
    statement, params = (ALL_CHUNKS, {}) if limit is None else (FIRST_CHUNKS, {"limit": limit})
    rows = graph().query(statement, {"file_id": file_id, **params})
    # A chunk written before Highlights shipped has no regions property -- Neo4j returns None for it,
    # which means "no Highlight" the same way an empty list does.
    return [{**row, "regions": json.loads(row.get("regions") or "[]")} for row in rows]


def _table_extraction(row: dict) -> dict:
    rows = json.loads(row.get("rows") or "[]")
    # Runs saved before rows had ids get their position as one; the first row deleted from such a
    # run writes the list back, which is what makes those ids stick from then on.
    for i, r in enumerate(rows):
        r.setdefault("id", str(i))
    return {**row, "columns": json.loads(row["columns"]), "rows": rows}


def create_table_extraction(file_id: str, request: str, columns: list[dict]) -> dict:
    """Anchored on MATCH (f:File ...), so a document deleted first leaves no orphaned TableExtraction."""
    extraction_id = str(uuid.uuid4())
    graph().query(CREATE_TABLE_EXTRACTION, {
        "id": extraction_id, "file_id": file_id, "request": request, "columns": json.dumps(columns),
    })
    return get_table_extraction(file_id, extraction_id)


def set_table_extraction(extraction_id: str, *, when_running: bool = False, **props) -> None:
    if "rows" in props:
        props["rows"] = json.dumps(props["rows"])
    statement = FINISH_TABLE_EXTRACTION if when_running else SET_TABLE_EXTRACTION
    graph().query(statement, {"id": extraction_id, "props": props})


def list_table_extractions(file_id: str) -> list[dict]:
    rows = graph().query(LIST_TABLE_EXTRACTIONS, {"file_id": file_id})
    return [_table_extraction(row["extraction"]) for row in rows]


def get_table_extraction(file_id: str, extraction_id: str) -> dict | None:
    rows = graph().query(GET_TABLE_EXTRACTION, {"id": extraction_id, "file_id": file_id})
    return _table_extraction(rows[0]["extraction"]) if rows else None


def delete_table_extraction(file_id: str, extraction_id: str) -> None:
    graph().query(DELETE_TABLE_EXTRACTION, {"id": extraction_id, "file_id": file_id})
