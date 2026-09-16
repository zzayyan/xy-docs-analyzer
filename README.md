# docs-analyzer

Document analyzer: vector RAG for short documents, section tree + knowledge graph for
long documents. Short documents get hybrid vector + fulltext search; documents past
`LONG_DOC_TOKENS` (default 20,000) also get a section outline and an entity/relationship
graph extracted per chunk.

Stack: FastAPI + LangGraph on the backend, Docling for ingest, Neo4j for storage
(vectors, fulltext, section tree, knowledge graph, chat history), a React + Vite
frontend styled with the XY Intelligence design system. LLM and embeddings each point
at Ollama or any OpenAI-compatible endpoint (vLLM, OpenRouter, OpenAI) independently.

## Run it

Three processes, three terminals.

**1. Neo4j**

```bash
docker compose up -d
```

**2. Backend**

```bash
cd backend
cp .env.example .env   # then fill in LLM_*/EMBED_* and NEO4J_* as needed
uv sync
uv run uvicorn app.api:app --reload
```

API on `http://localhost:8000`; `GET /docs` for the interactive schema.

**3. Frontend**

```bash
cd frontend
npm install
npm run dev
```

UI on `http://localhost:5173`.

## Configure a model provider

`backend/.env` sets `LLM_PROVIDER`/`EMBED_PROVIDER` independently, each `ollama` or
`openai` (the latter covers any OpenAI-compatible server: vLLM, OpenRouter, OpenAI
itself). See `backend/.env.example` for every field, including per-provider
`*_BASE_URL`/`*_API_KEY`/`*_MODEL`. A reasoning model behind an OpenAI-compatible
endpoint may need `reasoning_effort="none"` in `backend/app/models.py` — see the
comment there — or its answers stream out as pure reasoning tokens with an empty
`content`.

Switching embedding models after documents are already ingested is a breaking change:
`backend/app/db.py`'s `check_embedding_model` refuses to start if stored vectors don't
match the configured model/dimension, since vectors from different models aren't
comparable. Re-ingest every document (there's no in-place re-embed) or switch back.

## Tests

```bash
cd backend
uv run pytest tests/ -q --ignore=tests/test_smoke.py   # no infra needed
uv run pytest tests/test_smoke.py -q                    # needs Neo4j + a live LLM/embedding provider

cd frontend
npx tsc -b && npm run lint && npm run build
```

## Limits worth knowing

- **No PDF viewer, no re-ingest.** The uploaded file is deleted once ingest finishes;
  only the extracted text survives. A document that fails partway through has to be
  re-uploaded from your own copy, not retried in place.
- **No auth.** Every document is readable and deletable by anyone who can reach the
  API. Fine on localhost; don't bind `--host 0.0.0.0` without adding auth first.
- Ingest throughput is roughly 10-20 seconds per PDF page end to end (Docling
  conversion is most of that); `MAX_UPLOAD_MB` and `MAX_PAGES` in `backend/.env`
  bound how long an upload can make someone wait.
