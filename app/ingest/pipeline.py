import uuid

from app.config import settings
from app.db import graph
from app.ingest.convert import convert
from app.ingest.kg import extract_graph
from app.ingest.tree import build_tree
from app.models import embeddings


def set_status(file_id: str, **props) -> None:
    graph().query("MATCH (f:File {id: $id}) SET f += $props", {"id": file_id, "props": props})


def create_file(name: str) -> str:
    file_id = str(uuid.uuid4())
    graph().query(
        "CREATE (:File {id: $id, name: $name, status: 'queued', progress: 0.0})",
        {"id": file_id, "name": name},
    )
    return file_id


def progress_between(file_id: str, start: float, end: float):
    return lambda done, total: set_status(file_id, progress=round(start + (end - start) * done / total, 3))


def ingest(file_id: str, path: str) -> None:
    try:
        set_status(file_id, status="converting", progress=0.05)
        doc, tokens, chunks = convert(path)
        mode = "long" if tokens > settings.long_doc_tokens else "short"
        set_status(file_id, tokens=tokens, mode=mode, chunks=len(chunks), status="embedding", progress=0.3)

        vectors = embeddings().embed_documents([c["text"] for c in chunks])
        rows = [{**c, "id": f"{file_id}:{c['idx']}", "embedding": v} for c, v in zip(chunks, vectors)]
        graph().query(
            """
            MATCH (f:File {id: $file_id})
            UNWIND $rows AS r
            MERGE (c:Chunk {id: r.id})
            SET c.text = r.text, c.idx = r.idx, c.pages = r.pages, c.headings = r.headings,
                c.file_id = $file_id, c.embedding = r.embedding
            MERGE (c)-[:PART_OF]->(f)
            """,
            {"file_id": file_id, "rows": rows},
        )

        if mode == "long":
            set_status(file_id, status="building_tree", progress=0.35)
            build_tree(file_id, doc, rows, on_progress=progress_between(file_id, 0.35, 0.6))
            set_status(file_id, status="extracting_graph", progress=0.6)
            extract_graph(file_id, rows, on_progress=progress_between(file_id, 0.6, 0.95))

        set_status(file_id, status="done", progress=1.0)
    except Exception as exc:
        set_status(file_id, status="error", error=str(exc))
        raise
