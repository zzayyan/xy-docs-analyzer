import json
import uuid

from app.config import settings
from app.db import graph
from app.ingest.convert import convert
from app.ingest.kg import extract_graph
from app.ingest.tree import build_tree
from app.models import embeddings


def set_status(file_id: str, **props) -> None:
    graph().query(
        "MATCH (f:File {id: $id}) SET f += $props, f.updated_at = timestamp()",
        {"id": file_id, "props": props},
    )


def create_file(name: str) -> str:
    file_id = str(uuid.uuid4())
    graph().query(
        "CREATE (:File {id: $id, name: $name, status: 'queued', progress: 0.0, created_at: timestamp()})",
        {"id": file_id, "name": name},
    )
    return file_id


def progress_between(file_id: str, start: float, end: float):
    def on_progress(done: int, total: int) -> None:
        set_status(file_id, progress=round(start + (end - start) * done / total, 3), step_done=done, step_total=total)

    return on_progress


def ingest(file_id: str, path: str) -> None:
    try:
        set_status(file_id, status="converting", progress=0.05, step_done=0, step_total=0)
        doc, tokens, chunks = convert(path, on_progress=progress_between(file_id, 0.05, 0.3))
        mode = "long" if tokens > settings.long_doc_tokens else "short"
        # embedding is one call for every chunk at once, so it has no sub-progress of its own
        set_status(
            file_id, tokens=tokens, mode=mode, chunks=len(chunks),
            status="embedding", progress=0.3, step_done=0, step_total=0,
        )

        vectors = embeddings().embed_documents([c["text"] for c in chunks])
        rows = [{
            **c, "id": f"{file_id}:{c['idx']}", "embedding": v,
            # A Neo4j property can't hold a list of maps, the same reason Turn.citations is JSON too
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
            set_status(file_id, status="building_tree", progress=0.35, step_done=0, step_total=0)
            build_tree(file_id, doc, rows, on_progress=progress_between(file_id, 0.35, 0.6))
            set_status(file_id, status="extracting_graph", progress=0.6, step_done=0, step_total=0)
            extract_graph(file_id, rows, on_progress=progress_between(file_id, 0.6, 0.95))

        set_status(file_id, status="done", progress=1.0, step_done=0, step_total=0)
    except Exception as exc:
        set_status(file_id, status="error", error=str(exc))
        raise
