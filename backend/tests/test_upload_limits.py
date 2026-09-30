"""Upload caps reject oversized documents before any ingest work starts. Needs Neo4j only for the happy path."""
import pypdfium2
import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.config import settings

client = TestClient(app)


def make_pdf(path, pages: int) -> str:
    pdf = pypdfium2.PdfDocument.new()
    for _ in range(pages):
        pdf.new_page(200, 200)
    pdf.save(str(path))
    return str(path)


def test_oversized_file_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    big = tmp_path / "big.md"
    big.write_bytes(b"x" * (2 * 1024 * 1024))
    with big.open("rb") as f:
        response = client.post("/documents", files={"file": ("big.md", f, "text/markdown")})
    assert response.status_code == 413
    assert "1 MB" in response.json()["detail"]


def test_pdf_over_the_page_limit_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "max_pages", 2)
    path = make_pdf(tmp_path / "many.pdf", pages=3)
    with open(path, "rb") as f:
        response = client.post("/documents", files={"file": ("many.pdf", f, "application/pdf")})
    assert response.status_code == 413
    assert "3 pages" in response.json()["detail"]


def test_limits_endpoint_reports_the_active_caps(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 7)
    monkeypatch.setattr(settings, "max_pages", 9)
    assert client.get("/limits").json() == {"max_upload_mb": 7, "max_pages": 9}


def test_a_file_named_pdf_that_is_not_one_is_refused_and_not_kept(monkeypatch, tmp_path):
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    response = client.post("/documents", files={"file": ("x.pdf", b"not a pdf at all", "application/pdf")})
    assert response.status_code == 400
    assert list(tmp_path.iterdir()) == [], "the temp copy is deleted"
