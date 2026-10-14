"""Retrying an ingest from the kept Original. Store and ingest faked."""
from fastapi.testclient import TestClient

import app.api as api_module
import app.store as store_module
from app.api import app

client = TestClient(app)


def stub(monkeypatch, tmp_path, status: str, original: bool = True):
    files = {"d1": {"id": "d1", "name": "doc.pdf", "status": status, "progress": 0.4, "error": "model down"}}
    calls = []
    monkeypatch.setattr(store_module, "get_file", lambda doc_id: files.get(doc_id))
    monkeypatch.setattr(store_module, "reset_ingest", lambda doc_id: calls.append(("reset", doc_id)) or files[doc_id].update(status="queued", error=None, progress=0.0))
    monkeypatch.setattr(api_module, "ingest", lambda doc_id, path: calls.append(("ingest", doc_id, path)))
    path = tmp_path / "d1.pdf"
    if original:
        path.write_bytes(b"%PDF")
    monkeypatch.setattr(api_module, "original_path", lambda doc_id: path if original else None)
    return calls, path


def test_a_failed_document_is_reset_and_ingested_again_from_its_original(monkeypatch, tmp_path):
    calls, path = stub(monkeypatch, tmp_path, "error")

    response = client.post("/documents/d1/retry")

    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    assert calls == [("reset", "d1"), ("ingest", "d1", str(path))], "cleared before the new ingest starts"


def test_a_finished_document_can_be_ingested_again(monkeypatch, tmp_path):
    calls, path = stub(monkeypatch, tmp_path, "done")

    assert client.post("/documents/d1/retry").status_code == 200
    assert calls == [("reset", "d1"), ("ingest", "d1", str(path))]


def test_only_a_settled_document_with_its_original_can_be_retried(monkeypatch, tmp_path):
    calls, _ = stub(monkeypatch, tmp_path, "converting")
    assert client.post("/documents/d1/retry").status_code == 409

    calls, _ = stub(monkeypatch, tmp_path, "error", original=False)
    assert client.post("/documents/d1/retry").status_code == 409
    assert calls == [], "nothing reset when there is nothing to ingest from"
