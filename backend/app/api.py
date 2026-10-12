import io
import json
import mimetypes
import re
import shutil
import tempfile
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from neo4j.exceptions import ConstraintError
import openpyxl
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from pydantic import BaseModel

from app import auth, model_settings, store, table
from app.config import settings
from app.graph import MAX_HISTORY_TURNS, to_citations, workflow
from app.ingest.convert import page_count, render_page
from app.ingest.pipeline import create_file, ingest, set_status
from app.models import chat_model
from app.table import (
    Column, ProposedColumns, Stopped, SuggestedTables, document_context, propose_columns, suggest_tables,
)
from app.table import run as run_table

READ_CHUNK = 1024 * 1024

CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Ingests and Table Extractions run as in-process background tasks, so any restart (--reload on a
    # saved file included) kills them mid-way. Left as they were, they would read "running" forever and
    # a stuck Table Extraction would refuse every new one for its document.
    try:
        store.fail_interrupted("interrupted by a server restart")
        auth.ensure_admin()
        model_settings.load()
    except Exception as exc:
        # Neo4j down at boot: start anyway, the first request reports it the same way as before
        print(f"could not finish startup: {exc}")
    yield


# Every route needs a signed-in user except auth.PUBLIC_PATHS
app = FastAPI(title="Docs Analyzer", lifespan=lifespan, dependencies=[Depends(auth.require_user)])
# Credentials on: the session is a cookie, sent cross-origin from the Vite dev server
app.add_middleware(
    CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # A handler registered for the bare Exception class (as opposed to HTTPException) is wired
    # into Starlette's ServerErrorMiddleware, which wraps the whole app *outside* CORSMiddleware --
    # so its response skips CORS headers regardless of what CORSMiddleware is configured with. A
    # plain 500 (e.g. Neo4j unreachable) would otherwise reach the browser as an opaque CORS
    # failure instead of the real error. Adding the header here directly is the documented
    # workaround. No logging setup yet, so the detail is the exception text itself -- fine for
    # local dev, revisit if this API is ever exposed beyond localhost.
    origin = request.headers.get("origin")
    headers = (
        {"Access-Control-Allow-Origin": origin, "Access-Control-Allow-Credentials": "true"}
        if origin in CORS_ORIGINS else {}
    )
    return JSONResponse(status_code=500, content={"detail": str(exc)}, headers=headers)


class Login(BaseModel):
    username: str
    password: str


class User(BaseModel):
    id: str
    username: str
    role: str


class UserRow(User):
    created_at: int | None = None


class NewUser(BaseModel):
    username: str
    password: str
    role: Literal["admin", "user"] = "user"


class UserUpdate(BaseModel):
    """What an admin changes on someone else's account; a field left out stays as it is."""
    password: str | None = None
    role: Literal["admin", "user"] | None = None


class PasswordChange(BaseModel):
    current: str
    new: str


Provider = Literal["ollama", "openai"]


class ModelSettings(BaseModel):
    """The chat model and Table Extraction's own model. Keys go out masked; coming in, a key left as None
    keeps the stored one, so the form never has to hold a real key."""
    llm_provider: Provider
    llm_base_url: str
    llm_api_key: str | None = None
    llm_model: str
    llm_model_choices: str = ""
    llm_reasoning_effort: str | None = None
    table_llm_base_url: str = ""
    table_llm_api_key: str | None = None
    table_llm_model: str = ""


class ModelSettingsView(ModelSettings):
    # True once saved from Settings; False while every value still comes from .env
    saved: bool


class ModelTest(BaseModel):
    slot: Literal["chat", "table"]
    provider: Provider = "openai"
    base_url: str
    api_key: str | None = None
    model: str
    reasoning_effort: str | None = None


class ModelTestResult(BaseModel):
    ok: bool
    latency_ms: int
    reply: str | None = None
    error: str | None = None


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
    language: str | None = None  # the Document Language, detected at ingest
    has_original: bool = False
    # Pages in a PDF Original, for the document viewer; only on GET /documents/{id}, never on the list
    page_count: int | None = None


class ProposeRequest(BaseModel):
    request: str


class TableRequest(BaseModel):
    request: str
    columns: list[Column]
    # Skip the scope pass and read every chunk: the user saw the scoped run miss something
    read_all: bool = False


class Region(BaseModel):
    """One bounding box on one page of the Original -- what gets drawn as a Highlight."""

    page: int
    l: float
    t: float
    r: float
    b: float
    page_width: float
    page_height: float


class Citation(BaseModel):
    n: int
    chunk_id: str
    pages: list[int]
    headings: list[str]
    source: str
    text: str
    regions: list[Region] = []


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
    id: str
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
    chunks_done: int | None = None
    chunks_total: int | None = None
    # What the run read: the headings of the parts it chose, out of how many chunks the document has
    read_parts: list[str] | None = None
    document_chunks: int | None = None
    read_all: bool = False
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


class GraphNode(BaseModel):
    key: str
    name: str
    type: str | None = None
    mentions: int


class GraphEdge(BaseModel):
    source: str
    target: str
    type: str


class GraphData(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    total: int


class EntityDetail(BaseModel):
    entity: GraphNode
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    citations: list[Citation]


@app.post("/auth/login", response_model=User)
def login(body: Login, response: Response) -> dict:
    user = auth.authenticate(body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="wrong username or password")
    response.set_cookie(
        auth.COOKIE, auth.start_session(user["id"]), max_age=auth.SESSION_DAYS * 86400,
        httponly=True, samesite="lax", secure=settings.cookie_secure,
    )
    return user


@app.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response) -> None:
    auth.end_session(request.cookies[auth.COOKIE])
    response.delete_cookie(auth.COOKIE, httponly=True, samesite="lax", secure=settings.cookie_secure)


@app.get("/auth/me", response_model=User)
def me(user: dict = Depends(auth.require_user)) -> dict:
    return user


MIN_PASSWORD = 8
USERNAME = re.compile(r"[a-z0-9._-]{1,64}")


def checked_password(password: str) -> str:
    if len(password) < MIN_PASSWORD:
        raise HTTPException(status_code=400, detail=f"password must be at least {MIN_PASSWORD} characters")
    return password


@app.post("/auth/password", status_code=204)
def change_password(body: PasswordChange, request: Request, user: dict = Depends(auth.require_user)) -> None:
    """Your own password: the current one is asked again, so a session left open is not enough to take over."""
    if auth.authenticate(user["username"], body.current) is None:
        raise HTTPException(status_code=403, detail="current password is wrong")
    auth.set_password(user["id"], checked_password(body.new), keep_token=request.cookies[auth.COOKIE])


@app.get("/users", response_model=list[UserRow], dependencies=[Depends(auth.require_admin)])
def list_users() -> list[dict]:
    return auth.list_users()


@app.post("/users", response_model=User, dependencies=[Depends(auth.require_admin)])
def create_user(body: NewUser) -> dict:
    username = auth.normalize(body.username)
    if not USERNAME.fullmatch(username):
        raise HTTPException(status_code=400, detail="username: up to 64 of a-z, 0-9, dot, dash, underscore")
    try:
        return auth.create_user(username, checked_password(body.password), body.role)
    except ConstraintError:
        raise HTTPException(status_code=409, detail="username already taken")


def other_user(user_id: str, admin: dict) -> dict:
    """An admin never deletes or demotes their own account, so at least one admin always remains."""
    if user_id == admin["id"]:
        raise HTTPException(status_code=409, detail="not on your own account")
    user = auth.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return user


@app.patch("/users/{user_id}", status_code=204)
def update_user(user_id: str, body: UserUpdate, admin: dict = Depends(auth.require_admin)) -> None:
    other_user(user_id, admin)
    if body.password is not None:
        auth.set_password(user_id, checked_password(body.password))
    if body.role is not None:
        auth.set_role(user_id, body.role)


@app.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: str, admin: dict = Depends(auth.require_admin)) -> None:
    other_user(user_id, admin)
    auth.delete_user(user_id)


def get_file(doc_id: str) -> dict:
    file = store.get_file(doc_id)
    if file is None:
        raise HTTPException(status_code=404, detail="document not found")
    return file


def chat_history(doc_id: str) -> list[dict]:
    # Interrupted turns are noise, not a real prior exchange -- excluded rather than fed to
    # graph.py's contextualize/generate as if the partial answer were a complete one.
    return store.recent_turns(doc_id, MAX_HISTORY_TURNS)


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
    if path.lower().endswith(".pdf"):
        try:
            pages = page_count(path)
        except Exception:
            pages = 0
        if not pages:
            Path(path).unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="not a readable PDF")
        if pages > settings.max_pages:
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


def model_settings_view() -> dict:
    values = model_settings.current()
    for field in model_settings.SECRETS:
        values[field] = model_settings.masked(values[field])
    return {**values, "saved": bool(model_settings.saved())}


def checked_url(url: str, what: str) -> str:
    url = url.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail=f"{what}: a URL starting with http:// or https://")
    return url


@app.get("/settings/models", response_model=ModelSettingsView, dependencies=[Depends(auth.require_admin)])
def get_model_settings() -> dict:
    return model_settings_view()


@app.put("/settings/models", response_model=ModelSettingsView, dependencies=[Depends(auth.require_admin)])
def put_model_settings(body: ModelSettings) -> dict:
    stored = model_settings.current()
    values = {k: v.strip() if isinstance(v, str) else v for k, v in body.model_dump().items()}
    for field in model_settings.SECRETS:
        # A masked key echoed back is the stored key, never a new one
        if values[field] is None or values[field].startswith(model_settings.MASK):
            values[field] = stored[field]
    values["llm_base_url"] = checked_url(values["llm_base_url"], "chat model")
    if not values["llm_model"]:
        raise HTTPException(status_code=400, detail="chat model: a model name is required")
    if values["llm_provider"] == "openai" and not values["llm_api_key"]:
        raise HTTPException(status_code=400, detail="chat model: an OpenAI-compatible server needs an API key")
    if values["table_llm_model"]:
        values["table_llm_base_url"] = checked_url(values["table_llm_base_url"], "table model")
        if not values["table_llm_api_key"]:
            raise HTTPException(status_code=400, detail="table model: an API key is required")
    model_settings.save(values)
    return model_settings_view()


@app.delete("/settings/models", response_model=ModelSettingsView, dependencies=[Depends(auth.require_admin)])
def reset_model_settings() -> dict:
    """Back to the .env values."""
    model_settings.reset()
    return model_settings_view()


TEST_TIMEOUT_S = 30


@app.post("/settings/models/test", response_model=ModelTestResult, dependencies=[Depends(auth.require_admin)])
def test_model(body: ModelTest) -> dict:
    """One tiny call with the values in the form, saved or not, so a typo shows before anything breaks."""
    key = body.api_key
    if key is None or key.startswith(model_settings.MASK):
        key = model_settings.current()["llm_api_key" if body.slot == "chat" else "table_llm_api_key"]
    provider = body.provider if body.slot == "chat" else "openai"
    started = time.monotonic()
    try:
        client = chat_model(
            provider, checked_url(body.base_url, "URL"), key, body.model.strip(),
            max_tokens=256, reasoning_effort=body.reasoning_effort or None, timeout=TEST_TIMEOUT_S,
        )
        reply = client.invoke("Reply with the single word OK.").text
        return {"ok": True, "latency_ms": int((time.monotonic() - started) * 1000), "reply": reply.strip()[:200]}
    except HTTPException:
        raise
    except Exception as exc:
        return {"ok": False, "latency_ms": int((time.monotonic() - started) * 1000), "error": str(exc)[:500]}


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
    file = get_file(doc_id)
    path = original_path(doc_id)
    is_pdf = path is not None and mimetypes.guess_type(path)[0] == "application/pdf"
    return {**file, "has_original": path is not None, "page_count": page_count(path) if is_pdf else None}


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


@app.get("/documents/{doc_id}/original/pages/{page_no}")
def document_original_page(doc_id: str, page_no: int) -> Response:
    """A rendered page of a PDF Original, for the citation panel's Highlight view."""
    get_file(doc_id)
    path = original_path(doc_id)
    if path is None:
        raise HTTPException(status_code=404, detail="original not kept for this document")
    if mimetypes.guess_type(path)[0] != "application/pdf":
        raise HTTPException(status_code=404, detail="original is not a PDF")
    png = render_page(path, page_no)
    if png is None:
        raise HTTPException(status_code=404, detail="page not found")
    # An Original never changes once kept, and doc_id is a fresh id per upload, so this is safe forever
    return Response(png, media_type="image/png", headers={"Cache-Control": "public, max-age=31536000, immutable"})


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


@app.post("/documents/{doc_id}/retry", response_model=Document)
def retry_document(doc_id: str, background: BackgroundTasks) -> dict:
    """Ingest a Document again from its kept Original, so a failure late in a long ingest (or a server
    restart mid-way) costs a retry, not a re-upload. A finished Document can be ingested again too, to pick
    up what a newer ingest keeps (its tables, docs/adr/0005); never one whose ingest is still running."""
    file = get_file(doc_id)
    if file["status"] not in ("error", "done"):
        raise HTTPException(status_code=409, detail=f"the document is still being ingested (status: {file['status']})")
    path = original_path(doc_id)
    if path is None:
        raise HTTPException(status_code=409, detail="original not kept for this document, upload it again")
    store.reset_ingest(doc_id)
    background.add_task(ingest, doc_id, str(path))
    return {**get_file(doc_id), "has_original": True}


@app.get("/documents/{doc_id}/sections", response_model=list[Section])
def document_sections(doc_id: str) -> list[dict]:
    get_file(doc_id)
    return store.list_sections(doc_id)


@app.get("/documents/{doc_id}/sections/{section_id}/chunks", response_model=list[Chunk])
def document_section_chunks(doc_id: str, section_id: str) -> list[dict]:
    get_file(doc_id)
    return store.section_chunks(doc_id, section_id)


def extract_table(
    doc_id: str, table_id: str, request: str, columns: list[dict], model: str | None, read_all: bool = False,
) -> None:
    """The run itself, as a background task: minutes of LLM calls over every chunk, with its progress
    and its outcome kept on the TableExtraction so the user can leave the tab and come back.

    Like ingest, this occupies one of Starlette's sync worker threads for the whole run, and nothing
    caps how many runs a document can have in flight at once."""
    def progress(done: int, total: int) -> None:
        store.set_table_extraction(table_id, progress=round(done / total, 3), chunks_done=done, chunks_total=total)

    def cancelled() -> bool:
        extraction = store.get_table_extraction(doc_id, table_id)
        # A deleted document is a cancelled run too: there is nothing left to write the rows to
        return extraction is None or extraction["status"] == "cancelled"

    try:
        # Each chunk carries the tables it holds, read whole by the run instead of chunk by chunk (docs/adr/0005)
        tables = {t["id"]: t for t in store.list_doc_tables(doc_id)}
        document = [
            {**chunk, "tables": [tables[i] for i in chunk.get("table_ids") or [] if i in tables]}
            for chunk in store.list_chunks(doc_id)
        ]
        # Scoped to the parts that answer the request unless the user asked for everything (docs/adr/0004);
        # what was read is kept on the run, so a user can see what it skipped and re-run it on everything
        chunks = document if read_all else table.scope(request, document, model)
        store.set_table_extraction(
            table_id, status="running", chunks_done=0, chunks_total=len(chunks),
            read_parts=table.part_titles(chunks), document_chunks=len(document),
        )
        rows = run_table(chunks, columns, model, on_progress=progress, should_stop=cancelled, request=request)
        store.set_table_extraction(
            # A row's id is its position when the run finished; deleting a row never renumbers the rest
            # chunks_done/chunks_total stay as the last progress call left them: the chunks actually read,
            # which is fewer than the document's when the run was scoped to part of it
            table_id, status="done", progress=1.0, rows=[{**row, "id": str(i)} for i, row in enumerate(rows)],
            when_running=True,
        )
    except Stopped:
        # The user asked for this, so it is not an error and keeps no half-done rows
        store.set_table_extraction(table_id, status="cancelled")
    except Exception as exc:
        # The columns are left untouched, so the user can retry the same table without redefining it
        store.set_table_extraction(table_id, status="error", error=str(exc))


IN_FLIGHT = ("queued", "running")


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


def ready_document(doc_id: str) -> dict:
    """A document whose chunks exist: anything that reads them has nothing to read until ingest is done."""
    file = get_file(doc_id)
    if file["status"] != "done":
        raise HTTPException(status_code=409, detail=f"document is not ready (status: {file['status']})")
    return file


def table_context(doc_id: str) -> str:
    """What the document looks like, for a proposal to name its columns after."""
    return document_context(store.list_sections(doc_id), store.list_chunks(doc_id, limit=table.CONTEXT_CHUNKS))


@app.post("/documents/{doc_id}/tables/propose", response_model=ProposedColumns)
def propose_table_columns(doc_id: str, body: ProposeRequest) -> dict:
    """Proposes columns for the user to edit; nothing is stored until the run is created."""
    file = ready_document(doc_id)
    return {"columns": propose_columns(body.request, file.get("llm_model"), context=table_context(doc_id))}


@app.post("/documents/{doc_id}/tables/suggest", response_model=SuggestedTables)
def suggest_document_tables(doc_id: str) -> dict:
    """Tables worth pulling out of this document, for a user who has not typed a request yet. A POST,
    not a GET: it is an LLM call each time, so it runs when the user asks for it rather than on load."""
    file = ready_document(doc_id)
    return {"tables": suggest_tables(table_context(doc_id), file.get("llm_model"))}


@app.post("/documents/{doc_id}/tables", response_model=TableExtraction)
def create_table_extraction(doc_id: str, body: TableRequest, background: BackgroundTasks) -> dict:
    file = ready_document(doc_id)
    columns = checked_columns(body.columns)
    # One run at a time per document: each one holds a worker thread for minutes and hammers the same
    # model, and a user who clicks twice means "start it", not "start it twice".
    if any(e["status"] in IN_FLIGHT for e in store.list_table_extractions(doc_id)):
        raise HTTPException(status_code=409, detail="a table extraction is already running for this document")
    extraction = store.create_table_extraction(doc_id, body.request, columns, read_all=body.read_all)
    background.add_task(extract_table, doc_id, extraction["id"], body.request, columns, file.get("llm_model"), body.read_all)
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


@app.post("/documents/{doc_id}/tables/{table_id}/cancel", response_model=TableExtraction)
def cancel_table_extraction(doc_id: str, table_id: str) -> dict:
    """Marks the run cancelled; the background task notices between chunks and stops there."""
    extraction = document_table_extraction(doc_id, table_id)
    if extraction["status"] not in IN_FLIGHT:
        raise HTTPException(status_code=409, detail=f"table extraction is already {extraction['status']}")
    store.set_table_extraction(table_id, status="cancelled")
    return {**extraction, "status": "cancelled"}


@app.delete("/documents/{doc_id}/tables/{table_id}", status_code=204)
def delete_document_table_extraction(doc_id: str, table_id: str) -> None:
    # Also fine mid-run: the background task finds its TableExtraction gone, counts that as
    # cancelled, and stops at the next chunk (see extract_table's should_stop).
    document_table_extraction(doc_id, table_id)
    store.delete_table_extraction(doc_id, table_id)


@app.delete("/documents/{doc_id}/tables/{table_id}/rows/{row_id}", status_code=204)
def delete_table_row(doc_id: str, table_id: str, row_id: str) -> None:
    extraction = document_table_extraction(doc_id, table_id)
    if extraction["status"] in IN_FLIGHT:
        raise HTTPException(status_code=409, detail="the table extraction is still running")
    rows = [row for row in extraction["rows"] if row["id"] != row_id]
    if len(rows) == len(extraction["rows"]):
        raise HTTPException(status_code=404, detail="row not found")
    # ponytail: read-modify-write of the whole rows list, so two deletes landing at the same instant can
    # lose one. One person cleaning one table cannot click that fast; a Cypher-side edit if that changes.
    store.set_table_extraction(table_id, rows=rows)


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def cells(values: list) -> list:
    """Control characters (a form feed Docling kept, say) make openpyxl refuse the whole workbook."""
    return [ILLEGAL_CHARACTERS_RE.sub("", v) if isinstance(v, str) else v for v in values]


@app.get("/documents/{doc_id}/tables/{table_id}/export.xlsx")
def export_table_extraction(doc_id: str, table_id: str) -> Response:
    extraction = document_table_extraction(doc_id, table_id)
    if extraction["status"] != "done":
        raise HTTPException(status_code=409, detail=f"table extraction is {extraction['status']}, not done")
    names = [column["name"] for column in extraction["columns"]]
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(cells([*names, "Pages"]))
    for row in extraction["rows"]:
        # Every page any citation of the row points at, once each, in reading order
        pages = sorted({page for citation in row["citations"] for page in citation["pages"]})
        sheet.append(cells([*(row["values"].get(name, "") for name in names), ", ".join(map(str, pages)) or None]))
    # Values are quoted from the uploaded document, so a cell reading "=HYPERLINK(...)" must stay text:
    # openpyxl would otherwise store every string starting with "=" as a live formula
    for sheet_row in sheet.iter_rows():
        for cell in sheet_row:
            if cell.data_type == "f":
                cell.data_type = "s"
    buffer = io.BytesIO()
    workbook.save(buffer)
    # The request is typed by the user, in any script, and a header must be latin-1: keep only ASCII
    # letters, digits, spaces and dashes, collapse what is left, fall back to "table" if nothing is
    filename = " ".join(re.sub(r"[^A-Za-z0-9 _-]", " ", extraction["request"]).split())[:80] or "table"
    return Response(
        buffer.getvalue(), media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{filename}.xlsx"'},
    )


# ponytail: the Graph tab draws the most mentioned entities, not all of them (a 116-chunk thesis has ~1100);
# the rest are reached by expanding an entity's neighbours. Paginate or cluster if that stops being enough.
GRAPH_NODES = 120
ENTITY_NEIGHBOURS = 40
ENTITY_EVIDENCE = 20


@app.get("/documents/{doc_id}/graph", response_model=GraphData)
def document_graph(doc_id: str, limit: int = GRAPH_NODES) -> dict:
    """The knowledge graph's most mentioned entities and the relationships between them. A short
    document has no graph, which is an empty one here, not an error."""
    get_file(doc_id)
    return store.graph_top(doc_id, min(limit, 500))


@app.get("/documents/{doc_id}/graph/entity", response_model=EntityDetail)
def document_graph_entity(doc_id: str, key: str) -> dict:
    """One entity: its neighbours one step out, and the chunks that mention it as citations the source
    panel opens like a chat answer's. The key is a query parameter because entity names contain "/"."""
    get_file(doc_id)
    entity = store.entity(doc_id, key)
    if entity is None:
        raise HTTPException(status_code=404, detail="entity not found")
    neighbours = store.entity_neighbours(doc_id, key, ENTITY_NEIGHBOURS)
    nodes = list({n["key"]: {k: n[k] for k in ("key", "name", "type", "mentions")} for n in neighbours}.values())
    edges = [
        {"source": key, "target": n["key"], "type": n["rel"]} if n["outgoing"]
        else {"source": n["key"], "target": key, "type": n["rel"]}
        for n in neighbours
    ]
    chunks = store.entity_chunks(doc_id, key, ENTITY_EVIDENCE)
    return {
        "entity": entity, "nodes": nodes, "edges": edges,
        "citations": to_citations([{**chunk, "source": "kg"} for chunk in chunks]),
    }


@app.get("/documents/{doc_id}/turns", response_model=list[Turn])
def document_turns(doc_id: str) -> list[dict]:
    get_file(doc_id)
    return store.list_turns(doc_id)


@app.delete("/documents/{doc_id}/turns", status_code=204)
def clear_document_turns(doc_id: str) -> None:
    get_file(doc_id)
    store.clear_turns(doc_id)


def sse(event: str, data: object) -> str:
    # JSON-encode every payload, token strings included: a token containing a literal "\n" would
    # otherwise split the SSE "data:" line and corrupt the frame. json.dumps of a plain str still
    # produces a single-line quoted string, so this is correct for every event type below.
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def stream_answer(
    doc_id: str, question: str, mode: str, model: str | None = None, history: list[dict] | None = None,
    language: str | None = None,
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
    error: str | None = None
    try:
        async for kind, payload in workflow.astream(
            {"question": question, "doc_id": doc_id, "mode": mode, "model": model, "history": history or [],
             "language": language},
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
    except Exception as exc:
        error = str(exc)
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
    # Only after the Turn is saved: the client refetches history on either event, and a refetch that
    # beat the write would drop the answer it just watched stream. A disconnect never gets here.
    # Named "failed", not "error": EventSource reserves the name "error" for its own
    # connection-level failures (fired through onerror, no JSON .data payload) -- a custom SSE
    # event literally called "error" would collide with that on the client.
    yield sse("failed", {"detail": error}) if error is not None else sse("done", {"turn_id": turn_id})


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
        stream_answer(
            doc_id, question, file["mode"], model or file.get("llm_model"), chat_history(doc_id), file.get("language"),
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
