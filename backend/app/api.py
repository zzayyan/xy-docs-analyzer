import tempfile
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import store
from app.config import settings
from app.graph import workflow
from app.ingest.convert import page_count
from app.ingest.pipeline import create_file, ingest

READ_CHUNK = 1024 * 1024

app = FastAPI(title="Docs Analyzer")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    doc_id: str
    question: str


class Limits(BaseModel):
    max_upload_mb: int
    max_pages: int


class Upload(BaseModel):
    doc_id: str


class Document(BaseModel):
    id: str
    name: str
    status: str
    progress: float
    created_at: int | None = None
    updated_at: int | None = None
    mode: str | None = None
    tokens: int | None = None
    chunks: int | None = None
    error: str | None = None
    step_done: int | None = None
    step_total: int | None = None


class Citation(BaseModel):
    n: int
    chunk_id: str
    pages: list[int]
    headings: list[str]
    source: str
    text: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    mode: str
    turn_id: str


class Section(BaseModel):
    id: str
    title: str
    level: int
    order: int
    summary: str | None = None
    start_page: int | None = None
    end_page: int | None = None
    parent_id: str | None = None
    chunks: int


class Chunk(BaseModel):
    id: str
    idx: int
    text: str
    pages: list[int]
    headings: list[str]


class Turn(BaseModel):
    id: str
    question: str
    answer: str
    citations: list[Citation]
    mode: str
    complete: bool
    created_at: int


def get_file(doc_id: str) -> dict:
    file = store.get_file(doc_id)
    if file is None:
        raise HTTPException(status_code=404, detail="document not found")
    return file


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


@app.post("/documents", response_model=Upload)
def upload_document(file: UploadFile, background: BackgroundTasks) -> dict:
    path = save_upload(file)
    # Ingest runs for minutes per hundred pages, so refuse the work up front instead of timing the user out.
    # The page cap only applies to PDFs: page_count only knows how to read PDF page counts.
    if path.lower().endswith(".pdf") and (pages := page_count(path)) > settings.max_pages:
        Path(path).unlink(missing_ok=True)
        raise HTTPException(status_code=413, detail=f"PDF has {pages} pages, over the {settings.max_pages} page limit")

    doc_id = create_file(file.filename or Path(path).name)
    background.add_task(ingest_and_cleanup, doc_id, path)
    return {"doc_id": doc_id}


@app.get("/limits", response_model=Limits)
def limits() -> dict:
    return {"max_upload_mb": settings.max_upload_mb, "max_pages": settings.max_pages}


@app.get("/documents", response_model=list[Document])
def list_documents() -> list[dict]:
    return store.list_files()


@app.get("/documents/{doc_id}", response_model=Document)
def document_status(doc_id: str) -> dict:
    return get_file(doc_id)


@app.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: str) -> None:
    get_file(doc_id)  # 404 if missing
    # Safe even if an ingest is still writing: every write in app/ingest/* is anchored on MATCH (f:File
    # {id}) or on the chunks/sections it already created, so a delete here leaves nothing orphaned.
    store.delete_file(doc_id)


@app.get("/documents/{doc_id}/sections", response_model=list[Section])
def document_sections(doc_id: str) -> list[dict]:
    get_file(doc_id)
    return store.list_sections(doc_id)


@app.get("/documents/{doc_id}/sections/{section_id}/chunks", response_model=list[Chunk])
def document_section_chunks(doc_id: str, section_id: str) -> list[dict]:
    get_file(doc_id)
    return store.section_chunks(doc_id, section_id)


@app.get("/documents/{doc_id}/turns", response_model=list[Turn])
def document_turns(doc_id: str) -> list[dict]:
    get_file(doc_id)
    return store.list_turns(doc_id)


@app.delete("/documents/{doc_id}/turns", status_code=204)
def clear_document_turns(doc_id: str) -> None:
    get_file(doc_id)
    store.clear_turns(doc_id)


@app.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest) -> dict:
    file = get_file(body.doc_id)
    if file["status"] != "done":
        raise HTTPException(status_code=409, detail=f"document is not ready (status: {file['status']})")
    result = workflow.invoke({"question": body.question, "doc_id": body.doc_id, "mode": file["mode"]})
    turn = store.save_turn(
        body.doc_id, question=body.question, answer=result["answer"],
        citations=result["citations"], mode=file["mode"], complete=True,
    )
    return {"answer": result["answer"], "citations": result["citations"], "mode": file["mode"], "turn_id": turn["id"]}
