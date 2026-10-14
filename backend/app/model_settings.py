"""Model endpoints saved from Settings, on Meta nodes. They override .env and apply live, no restart."""
from langchain_neo4j import Neo4jGraph

from app import models
from app.config import settings
from app.db import graph

# Saved apart, so resetting the chat models to .env never changes what the stored vectors were embedded with
GROUPS = {
    "models": (
        "llm_provider", "llm_base_url", "llm_api_key", "llm_model", "llm_model_choices", "llm_reasoning_effort",
        "table_llm_base_url", "table_llm_api_key", "table_llm_model",
    ),
    # Not 'embedding': that Meta key is the marker of what the stored vectors were made with (app/db.py)
    "embedding_endpoint": ("embed_provider", "embed_base_url", "embed_api_key", "embed_model", "embed_dim"),
}
FIELDS = tuple(field for fields in GROUPS.values() for field in fields)
SECRETS = ("llm_api_key", "table_llm_api_key", "embed_api_key")
# Captured at import, before anything saved is applied: what a reset goes back to
ENV = {field: getattr(settings, field) for field in FIELDS}

READ = "OPTIONAL MATCH (m:Meta {key: $key}) RETURN m {.*} AS m"
WRITE = "MERGE (m:Meta {key: $key}) SET m = $props"
DELETE = "MATCH (m:Meta {key: $key}) DELETE m"

MASK = "••••"


def saved(group: str, g: Neo4jGraph | None = None) -> dict:
    row = (g or graph()).query(READ, {"key": group})[0]["m"] or {}
    return {field: row[field] for field in GROUPS[group] if field in row}


def apply(overrides: dict) -> None:
    # ponytail: this process only, so one uvicorn worker; with several, each would need to reload
    for field in FIELDS:
        setattr(settings, field, overrides.get(field, ENV[field]))
    # Neo4j stores no nulls, so "no reasoning_effort" is saved as ""
    settings.llm_reasoning_effort = settings.llm_reasoning_effort or None
    models._llm.cache_clear()
    models.table_llm.cache_clear()
    models.embeddings.cache_clear()


def load(g: Neo4jGraph | None = None) -> None:
    # db.graph() runs this before the embedding check, so the check sees the model actually in use
    apply({field: value for group in GROUPS for field, value in saved(group, g).items()})


def current() -> dict:
    return {field: getattr(settings, field) for field in FIELDS}


def save(group: str, values: dict) -> None:
    props = {**{field: values[field] for field in GROUPS[group]}, "key": group}
    if "llm_reasoning_effort" in props:
        props["llm_reasoning_effort"] = props["llm_reasoning_effort"] or ""
    graph().query(WRITE, {"key": group, "props": props})
    load()


def reset(group: str) -> None:
    graph().query(DELETE, {"key": group})
    load()


def masked(secret: str) -> str:
    return f"{MASK}{secret[-4:]}" if len(secret) > 8 else (MASK if secret else "")
