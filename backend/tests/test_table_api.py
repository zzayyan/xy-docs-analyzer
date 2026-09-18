"""HTTP API for Table Extractions. The store and the model are faked, so no Neo4j or LLM needed
(prior art: test_chat_stream.py)."""
import pytest
from fastapi.testclient import TestClient

import app.api as api_module
import app.store as store_module
import app.table as table_module
from app.api import app

client = TestClient(app)

COLUMNS = [{"name": "Kewajiban", "description": "The obligation"}]


def fake_document(doc_id: str, status: str = "done") -> dict:
    return {"id": doc_id, "name": "doc.pdf", "status": status, "mode": "short", "progress": 1.0,
            "created_at": 0, "updated_at": 0, "tokens": 10, "chunks": 1, "error": None,
            "step_done": None, "step_total": None, "llm_model": "qwen3:14b"}


@pytest.fixture
def stubbed(monkeypatch):
    """An in-memory stand-in for the Table Extractions of one document."""
    tables: dict[str, dict] = {}

    def create_table_extraction(file_id: str, request: str, columns: list[dict]) -> dict:
        row = {"id": "e1", "request": request, "columns": columns, "rows": [], "status": "queued",
               "progress": 0.0, "error": None, "created_at": 1, "updated_at": 1}
        tables[row["id"]] = row
        return row

    monkeypatch.setattr(store_module, "get_file", lambda doc_id: fake_document(doc_id))
    reads: list[int | None] = []

    def list_chunks(file_id: str, limit: int | None = None) -> list[dict]:
        reads.append(limit)
        return [{"id": "f:0", "text": "text", "pages": [1], "headings": []}]

    monkeypatch.setattr(store_module, "list_chunks", list_chunks)
    monkeypatch.setattr(store_module, "chunk_reads", reads, raising=False)
    monkeypatch.setattr(store_module, "create_table_extraction", create_table_extraction)
    monkeypatch.setattr(store_module, "set_table_extraction", lambda table_id, **props: tables[table_id].update(props))
    monkeypatch.setattr(store_module, "list_table_extractions", lambda file_id: list(tables.values()))
    monkeypatch.setattr(store_module, "get_table_extraction", lambda file_id, table_id: tables.get(table_id))
    return tables


def test_propose_returns_columns_and_stores_nothing(stubbed, monkeypatch):
    seen = {}
    monkeypatch.setattr(store_module, "list_sections", lambda file_id: [])
    monkeypatch.setattr(api_module, "propose_columns", lambda request, model, context: seen.update(request=request, model=model) or COLUMNS)

    response = client.post("/documents/d1/tables/propose", json={"request": "setiap kewajiban"})

    assert response.status_code == 200
    assert response.json() == {"columns": COLUMNS}
    assert seen == {"request": "setiap kewajiban", "model": "qwen3:14b"}, "proposal uses the document's model"
    assert stubbed == {}, "a proposal is not a Table Extraction yet"


def test_create_runs_the_extraction_in_the_background_and_saves_its_rows(stubbed, monkeypatch):
    rows = [{"values": {"Kewajiban": "bayar"}, "citations": [
        {"n": 1, "chunk_id": "f:0", "pages": [1], "headings": [], "source": "table", "text": "text"},
    ]}]
    monkeypatch.setattr(api_module, "run_table", lambda chunks, columns, model, on_progress, should_stop: rows)

    # TestClient runs background tasks before returning, so the run is finished here
    response = client.post("/documents/d1/tables", json={"request": "setiap kewajiban", "columns": COLUMNS})

    assert response.status_code == 200
    table_id = response.json()["id"]
    assert response.json()["status"] == "queued", "the response is the Table Extraction as created"

    saved = client.get(f"/documents/d1/tables/{table_id}").json()
    assert saved["status"] == "done"
    assert saved["progress"] == 1.0
    assert saved["rows"] == rows
    assert saved["columns"] == COLUMNS


def test_a_failed_run_is_stored_with_its_error_and_keeps_its_columns(stubbed, monkeypatch):
    def boom(chunks, columns, model, on_progress, should_stop):
        raise RuntimeError("model refused")

    monkeypatch.setattr(api_module, "run_table", boom)

    table_id = client.post("/documents/d1/tables", json={"request": "q", "columns": COLUMNS}).json()["id"]

    saved = client.get(f"/documents/d1/tables/{table_id}").json()
    assert saved["status"] == "error"
    assert saved["error"] == "model refused"
    assert saved["columns"] == COLUMNS


def test_create_is_409_while_the_document_is_still_ingesting(stubbed, monkeypatch):
    monkeypatch.setattr(store_module, "get_file", lambda doc_id: fake_document(doc_id, status="converting"))

    response = client.post("/documents/d1/tables", json={"request": "q", "columns": COLUMNS})

    assert response.status_code == 409
    assert stubbed == {}


def test_list_returns_the_documents_table_extractions(stubbed, monkeypatch):
    monkeypatch.setattr(api_module, "run_table", lambda chunks, columns, model, on_progress, should_stop: [])
    client.post("/documents/d1/tables", json={"request": "setiap kewajiban", "columns": COLUMNS})

    listed = client.get("/documents/d1/tables").json()

    assert [t["request"] for t in listed] == ["setiap kewajiban"]


def test_unknown_document_and_unknown_table_extraction_are_404(stubbed, monkeypatch):
    assert client.get("/documents/d1/tables/nope").status_code == 404
    monkeypatch.setattr(store_module, "get_file", lambda doc_id: None)
    assert client.get("/documents/nope/tables").status_code == 404
    assert client.post("/documents/nope/tables/propose", json={"request": "q"}).status_code == 404


def test_a_blank_or_repeated_column_name_is_refused_before_the_run_starts(stubbed):
    blank = client.post("/documents/d1/tables", json={"request": "q", "columns": [{"name": " ", "description": ""}]})
    assert blank.status_code == 400

    repeated = client.post("/documents/d1/tables", json={
        "request": "q", "columns": [{"name": "Kewajiban"}, {"name": "Kewajiban "}],
    })
    assert repeated.status_code == 400
    assert stubbed == {}, "nothing is stored and no run starts"


def test_propose_sends_the_documents_own_context_to_the_model(stubbed, monkeypatch):
    seen = {}
    monkeypatch.setattr(store_module, "list_sections", lambda file_id: [{"id": "s0", "title": "Bab I"}])
    monkeypatch.setattr(api_module, "propose_columns", lambda request, model, context: seen.update(context=context) or COLUMNS)

    response = client.post("/documents/d1/tables/propose", json={"request": "setiap kewajiban"})

    assert response.status_code == 200
    assert "Bab I" in seen["context"] and "text" in seen["context"]
    # The whole point of the limit: a 200-page document is not read in full to name three columns
    assert store_module.chunk_reads == [table_module.CONTEXT_CHUNKS]


def test_suggest_returns_candidate_tables_from_the_document_alone(stubbed, monkeypatch):
    suggestions = [{"title": "Kewajiban", "request": "Setiap kewajiban", "columns": COLUMNS}]
    monkeypatch.setattr(store_module, "list_sections", lambda file_id: [])
    monkeypatch.setattr(api_module, "suggest_tables", lambda context, model: suggestions)

    response = client.post("/documents/d1/tables/suggest")

    assert response.status_code == 200
    assert response.json() == {"tables": suggestions}
    assert stubbed == {}, "a suggestion is not a Table Extraction yet"


def test_suggest_is_409_while_the_document_is_still_ingesting(stubbed, monkeypatch):
    monkeypatch.setattr(store_module, "get_file", lambda doc_id: fake_document(doc_id, status="converting"))
    assert client.post("/documents/d1/tables/suggest").status_code == 409


def test_suggest_is_404_for_an_unknown_document(stubbed, monkeypatch):
    monkeypatch.setattr(store_module, "get_file", lambda doc_id: None)
    assert client.post("/documents/nope/tables/suggest").status_code == 404


def test_propose_is_409_while_the_document_is_still_ingesting(stubbed, monkeypatch):
    # Chunks are what the proposal reads; mid-ingest there is nothing to read yet
    monkeypatch.setattr(store_module, "get_file", lambda doc_id: fake_document(doc_id, status="embedding"))
    assert client.post("/documents/d1/tables/propose", json={"request": "q"}).status_code == 409


def test_a_second_run_is_refused_while_one_is_still_in_flight(stubbed, monkeypatch):
    monkeypatch.setattr(api_module, "run_table", lambda chunks, columns, model, on_progress, should_stop: [])
    first = client.post("/documents/d1/tables", json={"request": "q", "columns": COLUMNS})
    assert first.status_code == 200

    # The finished first run is not in flight, so it must not block a second one
    assert client.post("/documents/d1/tables", json={"request": "q", "columns": COLUMNS}).status_code == 200

    stubbed["e1"]["status"] = "running"
    blocked = client.post("/documents/d1/tables", json={"request": "q", "columns": COLUMNS})
    assert blocked.status_code == 409
    assert "already" in blocked.json()["detail"]


def test_cancelling_a_run_stops_it_and_records_that_the_user_stopped_it(stubbed, monkeypatch):
    stopped = []

    def slow_run(chunks, columns, model, on_progress, should_stop):
        # The run asks between chunks; the endpoint has already marked it cancelled by then
        stopped.append(should_stop())
        raise table_module.Stopped()

    monkeypatch.setattr(api_module, "run_table", slow_run)
    created = client.post("/documents/d1/tables", json={"request": "q", "columns": COLUMNS}).json()

    saved = client.get(f"/documents/d1/tables/{created['id']}").json()
    assert saved["status"] == "cancelled"
    assert saved["error"] is None, "a cancelled run is not a failed run"


def test_cancel_marks_a_running_extraction_and_is_refused_once_it_has_finished(stubbed, monkeypatch):
    monkeypatch.setattr(api_module, "run_table", lambda chunks, columns, model, on_progress, should_stop: [])
    table_id = client.post("/documents/d1/tables", json={"request": "q", "columns": COLUMNS}).json()["id"]

    assert client.post(f"/documents/d1/tables/{table_id}/cancel").status_code == 409, "the run already finished"

    stubbed[table_id]["status"] = "running"
    assert client.post(f"/documents/d1/tables/{table_id}/cancel").status_code == 200
    assert stubbed[table_id]["status"] == "cancelled"
    assert client.post("/documents/d1/tables/nope/cancel").status_code == 404


def test_progress_records_how_many_chunks_are_done(stubbed, monkeypatch):
    mid_run = {}

    def run_with_progress(chunks, columns, model, on_progress, should_stop):
        on_progress(1, len(chunks))
        mid_run.update(stubbed["e1"])
        return []

    monkeypatch.setattr(api_module, "run_table", run_with_progress)
    table_id = client.post("/documents/d1/tables", json={"request": "q", "columns": COLUMNS}).json()["id"]

    assert (mid_run["chunks_done"], mid_run["chunks_total"]) == (1, 1), "the count is visible while the run goes"
    saved = client.get(f"/documents/d1/tables/{table_id}").json()
    assert (saved["chunks_done"], saved["chunks_total"]) == (1, 1), "a finished run reads every chunk"
