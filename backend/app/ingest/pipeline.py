import json
import threading
import uuid

from pydantic import BaseModel, Field

from app.config import settings
from app.db import graph
from app.ingest.convert import convert, scanned_pages
from app.ingest.kg import extract_graph
from app.ingest.tree import build_tree
from app.models import embeddings, llm
from app.prompts import ingest as prompts

# Docling peaks at ~14 GB per batch, so two conversions at once can kill the worker. Only conversion is
# serialized; the LLM and embedding stages overlap freely.
# ponytail: one global lock; a bounded semaphore sized to RAM if several must convert at once
CONVERT_LOCK = threading.Lock()


LANGUAGE_SAMPLE_CHARS = 2000
EMBED_BATCH = 32


class DocumentLanguage(BaseModel):
    language: str = Field(description="The language's English name, e.g. English or Indonesian")


def detect_language(chunks: list[dict]) -> str | None:
    """None on failure: a missing language is better than a failed ingest."""
    sample = "\n\n".join(c["text"] for c in chunks)[:LANGUAGE_SAMPLE_CHARS]
    if not sample.strip():
        return None
    try:
        found = llm().with_structured_output(DocumentLanguage).invoke([("system", prompts.DETECT_LANGUAGE), ("human", sample)])
    except Exception:
        return None
    return found.language.strip() or None


class Deleted(Exception):
    """The Document was deleted mid-ingest."""


def set_status(file_id: str, **props) -> bool:
    """False when the File no longer exists. A new status also stamps when its stage began."""
    # Two parallel lists: a Neo4j property cannot hold a list of maps
    rows = graph().query(
        """
        MATCH (f:File {id: $id})
        SET f += $props, f.updated_at = timestamp()
        WITH f, $props.status AS stage
        SET f.stage_names = CASE WHEN stage IS NULL THEN f.stage_names ELSE coalesce(f.stage_names, []) + stage END,
            f.stage_starts = CASE WHEN stage IS NULL THEN f.stage_starts ELSE coalesce(f.stage_starts, []) + f.updated_at END
        RETURN count(f) AS n
        """,
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
        "CREATE (:File {id: $id, name: $name, status: 'queued', progress: 0.0, created_at: timestamp(), "
        "stage_names: ['queued'], stage_starts: [timestamp()]})",
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
            scanned = scanned_pages(path)
            step(file_id, ocr_pages=len(scanned))
            doc, tokens, chunks = convert(path, scanned, on_progress=progress_between(file_id, 0.05, 0.3))
        mode = "long" if tokens > settings.long_doc_tokens else "short"
        step(
            file_id, tokens=tokens, mode=mode, long_doc_tokens=settings.long_doc_tokens,
            chunks=len(chunks), language=detect_language(chunks),
            status="embedding", progress=0.3, step_done=0, step_total=len(chunks),
        )

        # Batched only so the UI can count chunks; one call would leave Embedding stuck at 0
        texts = [c["text"] for c in chunks]
        on_embedded = progress_between(file_id, 0.3, 0.35 if mode == "long" else 1.0)
        vectors = []
        for start in range(0, len(texts), EMBED_BATCH):
            vectors += embeddings().embed_documents(texts[start:start + EMBED_BATCH])
            on_embedded(len(vectors), len(texts))
        rows = [{
            **c, "id": f"{file_id}:{c['idx']}", "embedding": v,
            # A Neo4j property cannot hold a list of maps
            "regions": json.dumps(c["regions"]),
        } for c, v in zip(chunks, vectors)]
        graph().query(
            """
            MATCH (f:File {id: $file_id})
            UNWIND $rows AS r
            MERGE (c:Chunk {id: r.id})
            SET c.text = r.text, c.idx = r.idx, c.pages = r.pages, c.headings = r.headings,
                c.regions = r.regions, c.file_id = $file_id, c.embedding = r.embedding
            MERGE (c)-[:PART_OF]->(f)
            """,
            {"file_id": file_id, "rows": rows},
        )
        if mode == "long":
            step(file_id, status="building_tree", progress=0.35, step_done=0, step_total=0)
            sections = build_tree(file_id, doc, rows, on_progress=progress_between(file_id, 0.35, 0.6))
            step(file_id, sections=sections, status="extracting_graph", progress=0.6, step_done=0, step_total=len(rows))
            skipped = extract_graph(file_id, rows, on_progress=progress_between(file_id, 0.6, 0.95))
            [entities] = graph().query("MATCH (e:__Entity__ {file_id: $id}) RETURN count(e) AS n", {"id": file_id})
            step(file_id, graph_skipped=skipped, entities=entities["n"])

        set_status(file_id, status="done", progress=1.0, step_done=0, step_total=0)
    except Deleted:
        return
    except Exception as exc:
        set_status(file_id, status="error", error=str(exc))
        raise
