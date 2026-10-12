"""Model endpoints an admin sets in Settings. Saved values live on one Meta node and replace the .env values
(the defaults) for every field they hold; saving applies them to the live `settings` at once, no restart."""
from app import models
from app.config import settings
from app.db import graph

# The chat model (ingest, answers, the knowledge graph) and Table Extraction's own model
FIELDS = (
    "llm_provider", "llm_base_url", "llm_api_key", "llm_model", "llm_model_choices", "llm_reasoning_effort",
    "table_llm_base_url", "table_llm_api_key", "table_llm_model",
)
SECRETS = ("llm_api_key", "table_llm_api_key")
# Captured at import, before anything saved is applied: what a reset goes back to
ENV = {field: getattr(settings, field) for field in FIELDS}

READ = "OPTIONAL MATCH (m:Meta {key: 'models'}) RETURN m {.*} AS m"
WRITE = "MERGE (m:Meta {key: 'models'}) SET m = $props"
DELETE = "MATCH (m:Meta {key: 'models'}) DELETE m"


def saved() -> dict:
    row = graph().query(READ)[0]["m"] or {}
    return {field: row[field] for field in FIELDS if field in row}


def apply(overrides: dict) -> None:
    # ponytail: applied in this process only, so one uvicorn worker; with several, each would need to reload
    for field in FIELDS:
        setattr(settings, field, overrides.get(field, ENV[field]))
    # Neo4j stores no nulls, so "no reasoning_effort" is saved as ""
    settings.llm_reasoning_effort = settings.llm_reasoning_effort or None
    models._llm.cache_clear()
    models.table_llm.cache_clear()


def load() -> None:
    """At startup: what was saved in Settings wins over .env."""
    apply(saved())


def current() -> dict:
    return {field: getattr(settings, field) for field in FIELDS}


def save(values: dict) -> None:
    props = {**{field: values[field] for field in FIELDS}, "key": "models"}
    props["llm_reasoning_effort"] = props["llm_reasoning_effort"] or ""
    graph().query(WRITE, {"props": props})
    apply(values)


def reset() -> None:
    graph().query(DELETE)
    apply({})


MASK = "••••"


def masked(secret: str) -> str:
    """Enough of a key to recognise it, never enough to use it."""
    return f"{MASK}{secret[-4:]}" if len(secret) > 8 else (MASK if secret else "")
