"""Switching the embedding model once vectors are stored. Vectors from two models are not comparable, so
every chunk is embedded again from its stored text: no conversion and no LLM call, unlike a re-ingest.

The new vectors go to embedding_next first and replace the old ones in one statement at the end, together
with the marker and the saved settings, so search keeps working on the old model the whole time and a
failed run changes nothing."""
import threading

from app import model_settings
from app.db import graph
from app.models import embedding_model

EMBEDDED = "MATCH (c:Chunk) WHERE c.embedding IS NOT NULL RETURN count(c) AS n"
MARKER = "MATCH (m:Meta {key: 'embedding'}) RETURN m.model AS model, m.dim AS dim"
SET_MARKER = "MERGE (m:Meta {key: 'embedding'}) SET m.model = $model, m.dim = $dim"
FILES = "MATCH (c:Chunk) WHERE c.embedding IS NOT NULL RETURN DISTINCT c.file_id AS id"
FILE_CHUNKS = "MATCH (c:Chunk {file_id: $id}) WHERE c.embedding IS NOT NULL RETURN c.id AS id, c.text AS text"
WRITE_NEXT = "UNWIND $rows AS r MATCH (c:Chunk {id: r.id}) SET c.embedding_next = r.vector"
SWAP = "MATCH (c:Chunk) WHERE c.embedding_next IS NOT NULL SET c.embedding = c.embedding_next REMOVE c.embedding_next"
CLEAR_NEXT = "MATCH (c:Chunk) WHERE c.embedding_next IS NOT NULL REMOVE c.embedding_next"
IN_FLIGHT = "MATCH (f:File) WHERE NOT f.status IN ['done', 'error'] RETURN count(f) AS n"

# ponytail: progress lives in this process only; a restart mid-run leaves the old vectors in use and the
# run is simply started again (its leftover embedding_next values are cleared first)
STATE = {"status": "idle", "done": 0, "total": 0, "error": None}
LOCK = threading.Lock()


def running() -> bool:
    return STATE["status"] == "running"


def embedded_chunks() -> int:
    return graph().query(EMBEDDED)[0]["n"]


def ingests_in_flight() -> int:
    return graph().query(IN_FLIGHT)[0]["n"]


def marker() -> dict | None:
    rows = graph().query(MARKER)
    return rows[0] if rows else None


def set_marker(values: dict) -> None:
    graph().query(SET_MARKER, {"model": values["embed_model"], "dim": values["embed_dim"]})


def probe(values: dict) -> int:
    """The dimension the endpoint really returns, so a wrong EMBED_DIM is caught before any chunk is read."""
    client = embedding_model(values["embed_provider"], values["embed_base_url"], values["embed_api_key"], values["embed_model"])
    return len(client.embed_query("dimension check"))


def start(values: dict) -> bool:
    """Marks a run as started, or False when one already is. The caller runs run() in the background."""
    with LOCK:
        if running():
            return False
        STATE.update(status="running", done=0, total=0, error=None)
        return True


def run(values: dict) -> None:
    client = embedding_model(values["embed_provider"], values["embed_base_url"], values["embed_api_key"], values["embed_model"])
    try:
        graph().query(CLEAR_NEXT)
        files = [row["id"] for row in graph().query(FILES)]
        STATE["total"] = len(files)
        for file_id in files:
            chunks = graph().query(FILE_CHUNKS, {"id": file_id})
            vectors = client.embed_documents([chunk["text"] for chunk in chunks])
            if any(len(vector) != values["embed_dim"] for vector in vectors):
                raise RuntimeError(f"{values['embed_model']} returned vectors that are not {values['embed_dim']} long")
            graph().query(WRITE_NEXT, {"rows": [{"id": c["id"], "vector": v} for c, v in zip(chunks, vectors)]})
            STATE["done"] += 1
        graph().query(SWAP)
        set_marker(values)
        model_settings.save("embedding_endpoint", values)
        STATE["status"] = "done"
    except Exception as exc:
        graph().query(CLEAR_NEXT)
        STATE.update(status="error", error=str(exc)[:500])
