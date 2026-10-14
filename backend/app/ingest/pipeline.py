import json
import threading
import uuid

from pydantic import BaseModel, Field

from app.config import settings
from app.db import graph
from app.ingest.convert import convert
from app.ingest.kg import extract_graph
from app.ingest.tree import build_tree
from app.models import embeddings, llm

# Docling peaks at ~14 GB per batch, so two conversions at once can kill the worker. Only conversion is
# serialized; the LLM and embedding stages overlap freely.
# ponytail: one global lock; a bounded semaphore sized to RAM if several must convert at once
CONVERT_LOCK = threading.Lock()


LANGUAGE_SAMPLE_CHARS = 2000

LANGUAGE_SYSTEM = (
    "Name the language the text is written in, as its English name: English, Indonesian, and so on. If it "
    "mixes languages, name the one most of it is written in."
)


class DocumentLanguage(BaseModel):
    language: str = Field(description="The language's English name, e.g. English or Indonesian")


def detect_language(chunks: list[dict]) -> str | None:
    """None on failure: a missing language is better than a failed ingest."""
    sample = "\n\n".join(c["text"] for c in chunks)[:LANGUAGE_SAMPLE_CHARS]
    if not sample.strip():
        return None
    try:
        found = llm().with_structured_output(DocumentLanguage).invoke([("system", LANGUAGE_SYSTEM), ("human", sample)])
    except Exception:
        return None
    return found.language.strip() or None


class Deleted(Exception):
    """The Document was deleted mid-ingest."""


def set_status(file_id: str, **props) -> bool:
    """False when the File no longer exists."""
    rows = graph().query(
        "MATCH (f:File {id: $id}) SET f += $props, f.updated_at = timestamp() RETURN count(f) AS n",
        {"id": file_id, "props": props},
    )
    return bool(rows and rows[0]["n"])


def step(file_id: str, **props) -> None:
    """set_status that stops the ingest once the Document is gone."""
    if not set_status(file_id, **props):
        raise Deleted()


def create_file(name: str) -> str:
    file_id = str(uuid.uuid4())
    graph().query(
        "CREATE (:File {id: $id, name: $name, status: 'queued', progress: 0.0, created_at: timestamp()})",
        {"id": file_id, "name": name},
    )
    return file_id


def progress_between(file_id: str, start: float, end: float):
    def on_progress(done: int, total: int) -> None:
        step(file_id, progress=round(start + (end - start) * done / total, 3), step_done=done, step_total=total)

    return on_progress


def ingest(file_id: str, path: str) -> None:
    try:
        with CONVERT_LOCK:
            step(file_id, status="converting", progress=0.05, step_done=0, step_total=0)
            doc, tokens, chunks, tables = convert(path, on_progress=progress_between(file_id, 0.05, 0.3))
        mode = "long" if tokens > settings.long_doc_tokens else "short"
        step(
            file_id, tokens=tokens, mode=mode, chunks=len(chunks), language=detect_language(chunks),
            status="embedding", progress=0.3, step_done=0, step_total=0,
        )

        vectors = embeddings().embed_documents([c["text"] for c in chunks])
        rows = [{
            **c, "id": f"{file_id}:{c['idx']}", "embedding": v,
            # A Neo4j property cannot hold a list of maps
            "regions": json.dumps(c["regions"]),
            "table_ids": [f"{file_id}:t{i}" for i in c.get("table_refs") or []],
        } for c, v in zip(chunks, vectors)]
        graph().query(
            """
            MATCH (f:File {id: $file_id})
            UNWIND $rows AS r
            MERGE (c:Chunk {id: r.id})
            SET c.text = r.text, c.idx = r.idx, c.pages = r.pages, c.headings = r.headings,
                c.regions = r.regions, c.file_id = $file_id, c.embedding = r.embedding,
                c.table_ids = r.table_ids, c.prose = r.prose
            MERGE (c)-[:PART_OF]->(f)
            """,
            {"file_id": file_id, "rows": rows},
        )
        # CREATE, not MERGE: a retry clears the Document's DocTables first (store.RESET_INGEST)
        graph().query(
            """
            MATCH (f:File {id: $file_id})
            UNWIND $tables AS t
            CREATE (d:DocTable {id: t.id, file_id: $file_id, idx: t.idx, caption: t.caption,
                                markdown: t.markdown, pages: t.pages, regions: t.regions})
            CREATE (d)-[:PART_OF]->(f)
            """,
            {"file_id": file_id, "tables": [
                {**t, "id": f"{file_id}:t{t['idx']}", "regions": json.dumps(t["regions"])} for t in tables
            ]},
        )

        if mode == "long":
            step(file_id, status="building_tree", progress=0.35, step_done=0, step_total=0)
            build_tree(file_id, doc, rows, on_progress=progress_between(file_id, 0.35, 0.6))
            step(file_id, status="extracting_graph", progress=0.6, step_done=0, step_total=0)
            skipped = extract_graph(file_id, rows, on_progress=progress_between(file_id, 0.6, 0.95))
            step(file_id, graph_skipped=skipped)

        set_status(file_id, status="done", progress=1.0, step_done=0, step_total=0)
    except Deleted:
        return
    except Exception as exc:
        set_status(file_id, status="error", error=str(exc))
        raise
