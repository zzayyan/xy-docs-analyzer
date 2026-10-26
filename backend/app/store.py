"""Cypher for the API's reads and deletes. Ingest writes live in app/ingest/."""
import json

from app.db import graph

LIST_FILES = """
MATCH (f:File)
RETURN f {.*} AS file
ORDER BY coalesce(f.created_at, 0) DESC
"""

GET_FILE = "MATCH (f:File {id: $id}) RETURN f {.*} AS file"

# File first: ingest writes anchor on MATCH (f:File), so a running ingest stops writing and the sweeps
# below catch what it already wrote. File last would leave a window for orphaned chunks.
DELETE_FILE_CASCADE = [
    "MATCH (f:File {id: $id}) DETACH DELETE f",
    "MATCH (n:Chunk {file_id: $id}) DETACH DELETE n",
    "MATCH (n:Section {file_id: $id}) DETACH DELETE n",
    "MATCH (n:__Entity__ {file_id: $id}) DETACH DELETE n",
    "MATCH (n:Turn {file_id: $id}) DETACH DELETE n",
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

LIST_TURNS = """
MATCH (t:Turn {file_id: $file_id})
RETURN t.id AS id, t.question AS question, t.answer AS answer, t.citations AS citations,
       t.mode AS mode, t.complete AS complete, t.created_at AS created_at
ORDER BY t.created_at
"""

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


FAIL_INTERRUPTED = (
    "MATCH (f:File) WHERE NOT f.status IN ['done', 'error'] SET f.status = 'error', f.error = $error, f.updated_at = timestamp()"
)


def fail_interrupted(error: str) -> None:
    """Startup only: before any background task has begun, nothing unfinished can still be running."""
    graph().query(FAIL_INTERRUPTED, {"error": error})


# Edges only between two top entities, so none points at an undrawn node
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
    if not rows:
        return None
    file = rows[0]["file"]
    stages = zip(file.get("stage_names") or [], file.get("stage_starts") or [])
    return {**file, "timeline": [{"stage": stage, "started_at": at} for stage, at in stages]}


def delete_file(file_id: str) -> None:
    for statement in DELETE_FILE_CASCADE:
        graph().query(statement, {"id": file_id})


# Turns stay: a retry is the same Document
RESET_INGEST = [
    "MATCH (n:Chunk {file_id: $id}) DETACH DELETE n",
    "MATCH (n:Section {file_id: $id}) DETACH DELETE n",
    "MATCH (n:__Entity__ {file_id: $id}) DETACH DELETE n",
    "MATCH (f:File {id: $id}) SET f.status = 'queued', f.progress = 0.0, f.error = null, f.step_done = 0, "
    "f.step_total = 0, f.mode = null, f.tokens = null, f.chunks = null, f.graph_skipped = null, f.language = null, "
    "f.ocr_pages = null, f.long_doc_tokens = null, f.sections = null, f.entities = null, "
    "f.stage_names = ['queued'], f.stage_starts = [timestamp()], f.updated_at = timestamp()",
]


def reset_ingest(file_id: str) -> None:
    for statement in RESET_INGEST:
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
    return graph().query(RECENT_TURNS, {"file_id": file_id, "n": n})


def save_turn(
    file_id: str, *, question: str, answer: str, citations: list[dict], mode: str, complete: bool,
    turn_id: str,
) -> None:
    # Citations keep their chunk text, so history survives a re-ingest
    graph().query(SAVE_TURN, {
        "id": turn_id, "file_id": file_id, "question": question, "answer": answer,
        "citations": json.dumps(citations), "mode": mode, "complete": complete,
    })


def clear_turns(file_id: str) -> None:
    graph().query(CLEAR_TURNS, {"file_id": file_id})
