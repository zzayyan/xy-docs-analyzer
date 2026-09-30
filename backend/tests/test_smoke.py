"""End-to-end smoke tests. Need Neo4j (docker compose up -d) and a reachable LLM and embedding provider."""
import json

from fastapi.testclient import TestClient

from app.api import app
from app.config import settings
from app.db import graph

SAMPLE = """# Laporan Proyek Jembatan Sungai Brantas

## Anggaran
Total anggaran proyek adalah Rp 12,5 miliar yang didanai oleh APBD Provinsi Jawa Timur.

## Pelaksana
Kontraktor pelaksana adalah PT Karya Beton Nusantara dengan target selesai Desember 2027.
"""

client = TestClient(app)


def ask(doc_id: str, question: str) -> dict:
    """The answer and citations of one question, read off the SSE stream the UI uses."""
    events: dict[str, object] = {"token": ""}
    with client.stream("GET", "/chat/stream", params={"doc_id": doc_id, "question": question}) as r:
        assert r.status_code == 200
        for block in r.read().decode().split("

"):
            if not block.strip():
                continue
            event, data = (line.split(": ", 1)[1] for line in block.strip().split("
"))
            events[event] = events["token"] + json.loads(data) if event == "token" else json.loads(data)
    assert "done" in events, events
    return {"answer": events["token"], "citations": events.get("citations", [])}


def upload_sample(tmp_path) -> dict:
    sample = tmp_path / "laporan.md"
    sample.write_text(SAMPLE, encoding="utf-8")
    with sample.open("rb") as f:
        # TestClient runs background tasks before returning, so ingest is finished here
        response = client.post("/documents", files={"file": ("laporan.md", f, "text/markdown")})
    assert response.status_code == 200
    doc_id = response.json()["doc_id"]
    status = client.get(f"/documents/{doc_id}").json()
    assert status["status"] == "done", status
    assert status["chunks"] >= 1
    return status


def test_short_document_upload_then_chat(tmp_path):
    status = upload_sample(tmp_path)
    assert status["mode"] == "short"

    body = ask(status["id"], "Siapa kontraktor pelaksana proyek?")
    assert "Karya Beton" in body["answer"], body["answer"]
    assert body["citations"]


def test_long_document_builds_knowledge_graph(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "long_doc_tokens", 10)
    status = upload_sample(tmp_path)
    assert status["mode"] == "long"

    [row] = graph().query(
        """
        MATCH (:File {id: $id})<-[:PART_OF]-(:Chunk)-[:MENTIONS]->(e:__Entity__)
        WITH collect(DISTINCT e) AS entities
        RETURN size(entities) AS entities,
               COUNT { MATCH (a:__Entity__ {file_id: $id})-[]->(:__Entity__) } AS relationships,
               [e IN entities | e.key] AS keys,
               COUNT { MATCH (:File {id: $id})-[:HAS_SECTION]->(:Section) } AS root_sections,
               COUNT { MATCH (s:Section {file_id: $id}) WHERE s.summary IS NULL OR s.summary = '' } AS unsummarized,
               COUNT { MATCH (c:Chunk {file_id: $id})-[:IN_SECTION]->(:Section) } AS linked_chunks
        """,
        {"id": status["id"]},
    )
    assert row["root_sections"] >= 1, row
    assert row["unsummarized"] == 0, row
    assert row["linked_chunks"] == status["chunks"], row
    assert row["entities"] >= 2, row
    assert row["relationships"] >= 1, row
    assert any("karya beton" in key for key in row["keys"]), row["keys"]

    body = ask(status["id"], "Siapa kontraktor pelaksana proyek jembatan?")
    assert "Karya Beton" in body["answer"], body
    assert {c["source"] for c in body["citations"]} & {"tree", "kg", "kg_facts"}, body["citations"]
