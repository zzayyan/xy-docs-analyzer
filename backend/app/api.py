import json
import mimetypes
import shutil
import tempfile
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from app import store
from app.config import settings
from app.graph import to_citations, workflow
from app.ingest.convert import page_count
from app.ingest.pipeline import create_file, ingest, set_status
from app.table import Column, propose_columns
from app.table import run as run_table

READ_CHUNK = 1024 * 1024

CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

app = FastAPI(title="Docs Analyzer")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # A handler registered for the bare Exception class (as opposed to HTTPException) is wired
    # into Starlette's ServerErrorMiddleware, which wraps the whole app *outside* CORSMiddleware --
    # so its response skips CORS headers regardless of what CORSMiddleware is configured with. A
    # plain 500 (e.g. Neo4j unreachable) would otherwise reach the browser as an opaque CORS
    # failure instead of the real error. Adding the header here directly is the documented
    # workaround. No auth on this API and no logging setup yet, so the detail is the exception
    # text itself -- fine for local dev, revisit if this API is ever exposed beyond localhost.
    origin = request.headers.get("origin")
    headers = {"Access-Control-Allow-Origin": origin} if origin in CORS_ORIGINS else {}
    return JSONResponse(status_code=500, content={"detail": str(exc)}, headers=headers)


class ChatRequest(BaseModel):
    doc_id: str
    question: str


class Limits(BaseModel):
    max_upload_mb: int
    max_pages: int


class Models(BaseModel):
    models: list[str]
    default: str


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
    llm_model: str | None = None
    has_original: bool = False


class ProposeRequest(BaseModel):
    request: str


class ProposedColumns(BaseModel):
    columns: list[Column]


class TableRequest(BaseModel):
    request: str
    columns: list[Column]


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


class Row(BaseModel):
    values: dict[str, str]
    citations: list[Citation]


class TableExtraction(BaseModel):
    id: str
    request: str
    columns: list[Column]
    rows: list[Row]
    status: str
    progress: float
    error: str | None = None
    created_at: int
    updated_at: int


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


def chat_history(doc_id: str) -> list[dict]:
    # Interrupted turns are noise, not a real prior exchange -- excluded rather than fed to
    # graph.py's contextualize/generate as if the partial answer were a complete one.
    return [{"question": t["question"], "answer": t["answer"]} for t in store.list_turns(doc_id) if t["complete"]]


def original_path(doc_id: str) -> Path | None:
    """A Document's Original on disk, or None for Documents ingested before Originals were kept."""
    # "{id}*", not "{id}.*": an Original uploaded without an extension is stored as the bare id
    return next((settings.data_dir / "originals").glob(f"{doc_id}*"), None)


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
    originals = settings.data_dir / "originals"
    originals.mkdir(parents=True, exist_ok=True)
    # Keeps the extension: Docling picks the format from it, and the served content type is guessed from it
    original = originals / f"{doc_id}{Path(path).suffix.lower()}"
    shutil.move(path, original)
    background.add_task(ingest, doc_id, str(original))
    return {"doc_id": doc_id}


@app.get("/limits", response_model=Limits)
def limits() -> dict:
    return {"max_upload_mb": settings.max_upload_mb, "max_pages": settings.max_pages}


@app.get("/models", response_model=Models)
def models() -> dict:
    return {"models": settings.available_llm_models(), "default": settings.llm_model}


@app.get("/documents", response_model=list[Document])
def list_documents() -> list[dict]:
    return store.list_files()


@app.get("/documents/{doc_id}", response_model=Document)
def document_status(doc_id: str) -> dict:
    return {**get_file(doc_id), "has_original": original_path(doc_id) is not None}


@app.get("/documents/{doc_id}/original")
def document_original(doc_id: str) -> FileResponse:
    file = get_file(doc_id)
    path = original_path(doc_id)
    if path is None:
        raise HTTPException(status_code=404, detail="original not kept for this document")
    media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    # Only PDFs open inline. Anything else (an HTML Original especially) downloads instead, so an
    # uploaded page can never run script on the API's origin.
    disposition = "inline" if media_type == "application/pdf" else "attachment"
    return FileResponse(path, media_type=media_type, filename=file["name"], content_disposition_type=disposition)


@app.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: str) -> None:
    get_file(doc_id)  # 404 if missing
    # Safe even if an ingest is still writing: every write in app/ingest/* is anchored on MATCH (f:File
    # {id}) or on the chunks/sections it already created, so a delete here leaves nothing orphaned.
    # Original first: on Windows unlink fails while ingest still has it open, and failing before the
    # graph delete leaves a Document the user can retry deleting instead of an orphaned file.
    if path := original_path(doc_id):
        path.unlink(missing_ok=True)
    store.delete_file(doc_id)


@app.get("/documents/{doc_id}/sections", response_model=list[Section])
def document_sections(doc_id: str) -> list[dict]:
    get_file(doc_id)
    return store.list_sections(doc_id)


@app.get("/documents/{doc_id}/sections/{section_id}/chunks", response_model=list[Chunk])
def document_section_chunks(doc_id: str, section_id: str) -> list[dict]:
    get_file(doc_id)
    return store.section_chunks(doc_id, section_id)


def extract_table(doc_id: str, table_id: str, columns: list[dict], model: str | None) -> None:
    """The run itself, as a background task: minutes of LLM calls over every chunk, with its progress
    and its outcome kept on the TableExtraction so the user can leave the tab and come back.

    Like ingest, this occupies one of Starlette's sync worker threads for the whole run, and nothing
    caps how many runs a document can have in flight at once."""
    try:
        store.set_table_extraction(table_id, status="running")
        rows = run_table(
            store.list_chunks(doc_id), columns, model,
            on_progress=lambda done, total: store.set_table_extraction(table_id, progress=round(done / total, 3)),
        )
        store.set_table_extraction(table_id, status="done", progress=1.0, rows=rows)
    except Exception as exc:
        # The columns are left untouched, so the user can retry the same table without redefining it
        store.set_table_extraction(table_id, status="error", error=str(exc))


def checked_columns(columns: list[Column]) -> list[dict]:
    """A run is minutes of LLM calls over the whole document, so the columns are checked before it
    starts rather than after. Names key each row's values, so a blank or repeated name would silently
    drop a column's cells instead of failing."""
    named = [{"name": c.name.strip(), "description": c.description.strip()} for c in columns]
    names = [c["name"] for c in named]
    if not names or not all(names):
        raise HTTPException(status_code=400, detail="every column needs a name")
    if len(set(names)) != len(names):
        raise HTTPException(status_code=400, detail="column names must be unique")
    return named


@app.post("/documents/{doc_id}/tables/propose", response_model=ProposedColumns)
def propose_table_columns(doc_id: str, body: ProposeRequest) -> dict:
    """Proposes columns for the user to edit; nothing is stored until the run is created."""
    file = get_file(doc_id)
    return {"columns": propose_columns(body.request, file.get("llm_model"))}


@app.post("/documents/{doc_id}/tables", response_model=TableExtraction)
def create_table_extraction(doc_id: str, body: TableRequest, background: BackgroundTasks) -> dict:
    file = get_file(doc_id)
    if file["status"] != "done":
        raise HTTPException(status_code=409, detail=f"document is not ready (status: {file['status']})")
    columns = checked_columns(body.columns)
    extraction = store.create_table_extraction(doc_id, body.request, columns)
    background.add_task(extract_table, doc_id, extraction["id"], columns, file.get("llm_model"))
    return extraction


@app.get("/documents/{doc_id}/tables", response_model=list[TableExtraction])
def list_table_extractions(doc_id: str) -> list[dict]:
    get_file(doc_id)
    return store.list_table_extractions(doc_id)


@app.get("/documents/{doc_id}/tables/{table_id}", response_model=TableExtraction)
def document_table_extraction(doc_id: str, table_id: str) -> dict:
    get_file(doc_id)
    extraction = store.get_table_extraction(doc_id, table_id)
    if extraction is None:
        raise HTTPException(status_code=404, detail="table extraction not found")
    return extraction


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
    result = workflow.invoke({
        "question": body.question, "doc_id": body.doc_id, "mode": file["mode"],
        "model": file.get("llm_model"), "history": chat_history(body.doc_id),
    })
    turn = store.save_turn(
        body.doc_id, question=body.question, answer=result["answer"],
        citations=result["citations"], mode=file["mode"], complete=True,
    )
    return {"answer": result["answer"], "citations": result["citations"], "mode": file["mode"], "turn_id": turn["id"]}


def sse(event: str, data: object) -> str:
    # JSON-encode every payload, token strings included: a token containing a literal "\n" would
    # otherwise split the SSE "data:" line and corrupt the frame. json.dumps of a plain str still
    # produces a single-line quoted string, so this is correct for every event type below.
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def stream_answer(
    doc_id: str, question: str, mode: str, model: str | None = None, history: list[dict] | None = None,
) -> AsyncIterator[str]:
    # Must be a real async generator over workflow.astream(), not a sync generator over
    # workflow.stream(): a sync generator passed to StreamingResponse gets wrapped in
    # iterate_in_threadpool, which calls next() on it from a worker thread with no way to
    # interrupt that thread when the client disconnects -- nothing ever closes it, so the
    # "complete: False on disconnect" behavior below silently never fires (confirmed empirically:
    # killing a live client connection mid-stream left no Turn written after 17+ seconds). An
    # async generator gets real asyncio.CancelledError propagation when uvicorn cancels the
    # request task on disconnect, which is what actually makes the finally block below run promptly.
    turn_id = str(uuid.uuid4())
    answer_parts: list[str] = []
    citations: list[dict] = []
    complete = False
    try:
        async for kind, payload in workflow.astream(
            {"question": question, "doc_id": doc_id, "mode": mode, "model": model, "history": history or []},
            stream_mode=["updates", "messages"],
        ):
            if kind == "updates":
                node, output = next(iter(payload.items()))
                if node == "fuse":
                    # contexts are final before generate ever runs, so citations can go out --
                    # and the [n] markers become clickable -- before the first answer token
                    citations = to_citations(output["contexts"])
                    yield sse("citations", citations)
                elif node != "generate":
                    yield sse("status", {"node": node})
            elif kind == "messages":
                chunk, meta = payload
                # kg_retrieve's entity extraction and tree_search's section choice also produce
                # message chunks (both use structured output over the same LLM) -- without this
                # filter their raw JSON streams into the user-visible answer. Empty chunks (a
                # role-only first chunk, an empty stop chunk) are real but pointless to forward.
                if meta.get("langgraph_node") != "generate" or not chunk.text:
                    continue
                answer_parts.append(chunk.text)
                yield sse("token", chunk.text)
        complete = True
        yield sse("done", {"turn_id": turn_id})
    except Exception as exc:
        # Named "failed", not "error": EventSource reserves the name "error" for its own
        # connection-level failures (fired through onerror, no JSON .data payload) -- a custom SSE
        # event literally called "error" would collide with that on the client.
        yield sse("failed", {"detail": str(exc)})
    finally:
        # Runs even if the client disconnects mid-stream: uvicorn cancels the request's asyncio
        # Task, which raises CancelledError at whatever await this generator is suspended on
        # (inside workflow.astream() or at our own yield) -- CancelledError is a BaseException, so
        # `except Exception` above does not swallow it, and it keeps propagating after this block,
        # as cancellation must. complete stays False in that case, so the partial answer is still
        # visible in history rather than silently lost. Anchored on MATCH (f:File ...) inside
        # save_turn, so a document deleted mid-answer makes this a no-op, not an orphaned Turn.
        store.save_turn(
            doc_id, question=question, answer="".join(answer_parts),
            citations=citations, mode=mode, complete=complete, turn_id=turn_id,
        )


@app.get("/chat/stream")
def chat_stream(doc_id: str, question: str, model: str | None = None) -> StreamingResponse:
    # 404/409 are raised here, before StreamingResponse starts -- so "document not found" or "not
    # ready" are still real HTTP status codes, not something buried inside a 200 event stream.
    file = get_file(doc_id)
    if file["status"] != "done":
        raise HTTPException(status_code=409, detail=f"document is not ready (status: {file['status']})")
    # A mismatch here means stale frontend state (its /models list is out of date with .env), not
    # a plausible user typo -- the picker is a dropdown, not free text -- so this fails loud rather
    # than silently falling back to the stored default.
    if model is not None and model not in settings.available_llm_models():
        raise HTTPException(status_code=400, detail=f"unknown model: {model}")
    # Switching models here is meant to stick, like Claude's own model switcher: the next reload
    # (or the next question, if the user doesn't touch the picker again) keeps using it.
    if model is not None and model != file.get("llm_model"):
        set_status(doc_id, llm_model=model)
    return StreamingResponse(
        stream_answer(doc_id, question, file["mode"], model or file.get("llm_model"), chat_history(doc_id)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
