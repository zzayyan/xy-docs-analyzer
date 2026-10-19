# docs-analyzer

Laporan tugas besar (Bahasa Indonesia): [docs/laporan-tugas-besar.md](docs/laporan-tugas-besar.md)

Document analyzer: hybrid vector + fulltext search for every document, plus a section
tree and a knowledge graph for long ones. Documents past `LONG_DOC_TOKENS` (default
20,000) also get a section outline and an entity/relationship graph extracted per chunk,
searched alongside the vectors.

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
endpoint (Qwen3.5 on vLLM, for one) needs `LLM_REASONING_EFFORT=none`, or its answers
stream out as pure reasoning tokens with an empty `content`. Leave it unset for
OpenAI's own models, which reject the parameter.

Switching embedding models after documents are already ingested is a breaking change:
`backend/app/db.py`'s `check_embedding_model` fails every request, from the first one,
with a message saying how to reset, if stored vectors don't match the configured
model/dimension, since vectors from different models aren't
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

- **Originals are kept until their Document is deleted.** Each Document's Original is
  stored exactly as received under `DATA_DIR` (default `backend/data/originals/`) and
  opens from the Document header's "Original" link; deleting the Document deletes its
  Original. Documents ingested
  before this change have no Original. A document that fails partway through (a server
  restart, including `--reload` picking up a saved file, marks it failed too) can be
  retried from its Original with "Try again"; one ingested before Originals were kept
  has to be re-uploaded.
- **One PDF converts at a time.** Docling peaks at ~14 GB per 25-page batch, so a second
  upload stays `queued` until the first finishes converting.
- **No auth.** Every document is readable and deletable by anyone who can reach the
  API. Fine on localhost; don't bind `--host 0.0.0.0` without adding auth first.
- Ingest throughput is roughly 10-20 seconds per PDF page end to end (Docling
  conversion is most of that); `MAX_UPLOAD_MB` and `MAX_PAGES` in `backend/.env`
  bound how long an upload can make someone wait.
