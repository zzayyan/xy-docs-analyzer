import shutil
import tempfile
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile
from pydantic import BaseModel

from app.db import graph
from app.graph import workflow
from app.ingest.pipeline import create_file, ingest

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


@app.post("/documents")
def upload_document(file: UploadFile, background: BackgroundTasks) -> dict:
    # Keep the original suffix: Docling picks the format from it
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename or "").suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
    doc_id = create_file(file.filename or Path(tmp.name).name)
    background.add_task(ingest_and_cleanup, doc_id, tmp.name)
    return {"doc_id": doc_id}


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
