"""Live check of the configured model servers (LLM_* and EMBED_* in .env). Needs both servers reachable."""
import math

from app.config import settings
from app.models import embeddings, llm


def test_llm_answers():
    reply = llm(max_tokens=20).invoke("What is the capital of Sweden? Answer in one word.")
    assert "stockholm" in reply.content.lower(), reply.content


def test_embeddings_return_configured_dimension():
    query = embeddings().embed_query("Berapa total anggaran proyek?")
    docs = embeddings().embed_documents(["Total anggaran Rp 12,5 miliar.", "Kontraktor PT Karya Beton Nusantara."])

    assert len(query) == settings.embed_dim
    assert [len(v) for v in docs] == [settings.embed_dim] * 2
    # bge-m3 returns unit vectors; a zero or garbage vector would fail here
    assert math.isclose(math.hypot(*query), 1.0, abs_tol=1e-3)
