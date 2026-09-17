"""HTTP API for Table Extractions. The store and the model are faked, so no Neo4j or LLM needed
(prior art: test_chat_stream.py)."""
import pytest
from fastapi.testclient import TestClient

import app.api as api_module
import app.store as store_module
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
    monkeypatch.setattr(store_module, "list_chunks", lambda file_id: [
        {"id": "f:0", "text": "text", "pages": [1], "headings": []},
    ])
    monkeypatch.setattr(store_module, "create_table_extraction", create_table_extraction)
    monkeypatch.setattr(store_module, "set_table_extraction", lambda table_id, **props: tables[table_id].update(props))
    monkeypatch.setattr(store_module, "list_table_extractions", lambda file_id: list(tables.values()))
    monkeypatch.setattr(store_module, "get_table_extraction", lambda file_id, table_id: tables.get(table_id))
    return tables


def test_propose_returns_columns_and_stores_nothing(stubbed, monkeypatch):
    seen = {}
    monkeypatch.setattr(api_module, "propose_columns", lambda request, model: seen.update(request=request, model=model) or COLUMNS)

    response = client.post("/documents/d1/tables/propose", json={"request": "setiap kewajiban"})

    assert response.status_code == 200
    assert response.json() == {"columns": COLUMNS}
    assert seen == {"request": "setiap kewajiban", "model": "qwen3:14b"}, "proposal uses the document's model"
    assert stubbed == {}, "a proposal is not a Table Extraction yet"


def test_create_runs_the_extraction_in_the_background_and_saves_its_rows(stubbed, monkeypatch):
    rows = [{"values": {"Kewajiban": "bayar"}, "citations": [
        {"n": 1, "chunk_id": "f:0", "pages": [1], "headings": [], "source": "table", "text": "text"},
    ]}]
    monkeypatch.setattr(api_module, "run_table", lambda chunks, columns, model, on_progress: rows)

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
    def boom(chunks, columns, model, on_progress):
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
    monkeypatch.setattr(api_module, "run_table", lambda chunks, columns, model, on_progress: [])
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
