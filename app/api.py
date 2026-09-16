import tempfile
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import settings
from app.db import graph
from app.graph import workflow
from app.ingest.convert import page_count
from app.ingest.pipeline import create_file, ingest

READ_CHUNK = 1024 * 1024

app = FastAPI(title="Docs Analyzer")


class ChatRequest(BaseModel):
    doc_id: str
    question: str


def get_file(doc_id: str) -> dict:
    rows = graph().query("MATCH (f:File {id: $id}) RETURN f {.*} AS file", {"id": doc_id})
    if not rows:
        raise HTTPException(status_code=404, detail="document not found")
    return rows[0]["file"]


def ingest_and_cleanup(doc_id: str, path: str) -> None:
    try:
        ingest(doc_id, path)
    finally:
        Path(path).unlink(missing_ok=True)


def save_upload(file: UploadFile) -> str:
    """Stream the upload to a temp file, stopping as soon as it passes the size cap."""
    limit = settings.max_upload_mb * 1024 * 1024
    # Keep the original suffix: Docling picks the format from it
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename or "").suffix)
    try:
        written = 0
        with tmp:
            while chunk := file.file.read(READ_CHUNK):
                written += len(chunk)
                if written > limit:
                    raise HTTPException(status_code=413, detail=f"file is larger than {settings.max_upload_mb} MB")
                tmp.write(chunk)
    except BaseException:
        Path(tmp.name).unlink(missing_ok=True)
        raise
    return tmp.name


@app.post("/documents")
def upload_document(file: UploadFile, background: BackgroundTasks) -> dict:
    path = save_upload(file)
    # Ingest runs for minutes per hundred pages, so refuse the work up front instead of timing the user out
    if path.lower().endswith(".pdf") and (pages := page_count(path)) > settings.max_pages:
        Path(path).unlink(missing_ok=True)
        raise HTTPException(status_code=413, detail=f"PDF has {pages} pages, over the {settings.max_pages} page limit")

    doc_id = create_file(file.filename or Path(path).name)
    background.add_task(ingest_and_cleanup, doc_id, path)
    return {"doc_id": doc_id}


@app.get("/limits")
def limits() -> dict:
    return {"max_upload_mb": settings.max_upload_mb, "max_pages": settings.max_pages}


@app.get("/documents/{doc_id}")
def document_status(doc_id: str) -> dict:
    return get_file(doc_id)


@app.post("/chat")
def chat(body: ChatRequest) -> dict:
    file = get_file(body.doc_id)
    if file["status"] != "done":
        raise HTTPException(status_code=409, detail=f"document is not ready (status: {file['status']})")
    result = workflow.invoke({"question": body.question, "doc_id": body.doc_id, "mode": file["mode"]})
    return {"answer": result["answer"], "citations": result["citations"], "mode": file["mode"]}
