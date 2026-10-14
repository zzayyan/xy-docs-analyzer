"""GET /documents/{doc_id}/original/pages/{page_no}. Store faked."""
import pytest
from fastapi.testclient import TestClient

import app.api as api_module
import app.store as store_module
from app.api import app
from app.config import settings

client = TestClient(app)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def ingested(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    files: dict[str, dict] = {}

    def create_file(name: str) -> str:
        files["d1"] = {"id": "d1", "name": name, "status": "done", "progress": 1.0}
        return "d1"

    monkeypatch.setattr(api_module, "create_file", create_file)
    monkeypatch.setattr(api_module, "ingest", lambda doc_id, path: None)
    monkeypatch.setattr(store_module, "get_file", lambda doc_id: files.get(doc_id))
    return files


def upload_pdf(pages: int, name: str = "report.pdf") -> str:
    import io

    import pypdfium2

    pdf = pypdfium2.PdfDocument.new()
    for _ in range(pages):
        pdf.new_page(200, 200)
    buffer = io.BytesIO()
    pdf.save(buffer)
    response = client.post("/documents", files={"file": (name, buffer.getvalue(), "application/pdf")})
    assert response.status_code == 200
    return response.json()["doc_id"]


def test_a_page_of_a_kept_pdf_original_renders_as_png(ingested):
    doc_id = upload_pdf(pages=2)

    response = client.get(f"/documents/{doc_id}/original/pages/2")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(PNG_MAGIC)
    assert "immutable" in response.headers["cache-control"]


def test_a_page_out_of_range_is_404(ingested):
    doc_id = upload_pdf(pages=2)

    assert client.get(f"/documents/{doc_id}/original/pages/0").status_code == 404
    assert client.get(f"/documents/{doc_id}/original/pages/3").status_code == 404


def test_an_unknown_document_is_404(ingested):
    assert client.get("/documents/nope/original/pages/1").status_code == 404


def test_a_document_with_no_kept_original_is_404(ingested, monkeypatch):
    monkeypatch.setattr(store_module, "get_file", lambda doc_id: {"id": doc_id, "name": "old.pdf", "status": "done", "progress": 1.0})
    assert client.get("/documents/old/original/pages/1").status_code == 404


def test_a_non_pdf_original_is_404(ingested):
    response = client.post("/documents", files={"file": ("notes.md", b"# hi", "text/markdown")})
    doc_id = response.json()["doc_id"]

    assert client.get(f"/documents/{doc_id}/original/pages/1").status_code == 404


def test_a_pdf_original_reports_its_page_count_for_the_document_viewer(ingested):
    doc_id = upload_pdf(pages=3)
    assert client.get(f"/documents/{doc_id}").json()["page_count"] == 3


def test_a_non_pdf_or_missing_original_has_no_page_count(ingested, monkeypatch):
    doc_id = client.post("/documents", files={"file": ("notes.md", b"# hi", "text/markdown")}).json()["doc_id"]
    assert client.get(f"/documents/{doc_id}").json()["page_count"] is None

    monkeypatch.setattr(store_module, "get_file", lambda doc_id: {"id": doc_id, "name": "old.pdf", "status": "done", "progress": 1.0})
    assert client.get("/documents/old").json()["page_count"] is None
