"""Originals: kept on upload, served, removed with their Document. Store and ingest faked."""
import io

import pypdfium2
import pytest
from fastapi.testclient import TestClient

import app.api as api_module
import app.store as store_module
from app.api import app
from app.config import settings

client = TestClient(app)


@pytest.fixture
def ingested(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    files: dict[str, dict] = {}

    def create_file(name: str) -> str:
        files["d1"] = {"id": "d1", "name": name, "status": "done", "progress": 1.0}
        return "d1"

    ingested = []
    monkeypatch.setattr(api_module, "create_file", create_file)
    monkeypatch.setattr(api_module, "ingest", lambda doc_id, path: ingested.append(path))
    monkeypatch.setattr(store_module, "get_file", lambda doc_id: files.get(doc_id))
    monkeypatch.setattr(store_module, "delete_file", lambda doc_id: files.pop(doc_id))
    return ingested


def make_pdf() -> bytes:
    pdf = pypdfium2.PdfDocument.new()
    pdf.new_page(200, 200)
    buffer = io.BytesIO()
    pdf.save(buffer)
    return buffer.getvalue()


def upload(name: str, content: bytes, content_type: str) -> str:
    response = client.post("/documents", files={"file": (name, content, content_type)})
    assert response.status_code == 200
    return response.json()["doc_id"]


def test_upload_keeps_the_original_keyed_by_document_id(ingested):
    doc_id = upload("laporan.md", b"# Hello", "text/markdown")

    original = settings.data_dir / "originals" / f"{doc_id}.md"
    assert original.read_bytes() == b"# Hello"
    assert ingested == [str(original)], "ingest reads the kept Original, and it survives ingest"
    assert client.get(f"/documents/{doc_id}").json()["has_original"] is True


def test_original_is_served_as_uploaded_with_its_content_type(ingested):
    doc_id = upload("laporan.md", b"# Hello", "text/markdown")

    response = client.get(f"/documents/{doc_id}/original")
    assert response.status_code == 200
    assert response.content == b"# Hello"
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"].startswith("attachment"), "only PDFs open inline"


def test_pdf_original_opens_inline(ingested):
    doc_id = upload("report.pdf", make_pdf(), "application/pdf")

    response = client.get(f"/documents/{doc_id}/original")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline")


def test_original_is_404_for_unknown_document(ingested):
    assert client.get("/documents/nope/original").status_code == 404


def test_original_is_404_for_document_ingested_before_originals_were_kept(ingested, monkeypatch):
    monkeypatch.setattr(store_module, "get_file", lambda doc_id: {"id": doc_id, "name": "old.pdf", "status": "done", "progress": 1.0})
    assert client.get("/documents/old/original").status_code == 404
    assert client.get("/documents/old").json()["has_original"] is False


def test_deleting_a_document_removes_its_original(ingested):
    doc_id = upload("laporan.md", b"# Hello", "text/markdown")
    original = settings.data_dir / "originals" / f"{doc_id}.md"
    assert original.exists()

    assert client.delete(f"/documents/{doc_id}").status_code == 204
    assert not original.exists()
