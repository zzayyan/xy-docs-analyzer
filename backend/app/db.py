from functools import lru_cache

from langchain_neo4j import Neo4jGraph

from app.config import settings

SCHEMA = [
    "CREATE CONSTRAINT file_id IF NOT EXISTS FOR (f:File) REQUIRE f.id IS UNIQUE",
    "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT section_id IF NOT EXISTS FOR (s:Section) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT turn_id IF NOT EXISTS FOR (t:Turn) REQUIRE t.id IS UNIQUE",
    "CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE",
    "CREATE CONSTRAINT user_username IF NOT EXISTS FOR (u:User) REQUIRE u.username IS UNIQUE",
    "CREATE CONSTRAINT session_id IF NOT EXISTS FOR (s:Session) REQUIRE s.id IS UNIQUE",
    # Concurrent first startups could each MERGE a marker; drop extras so the constraint can be created
    "MATCH (m:Meta) WITH m.key AS key, collect(m) AS ms WHERE size(ms) > 1 UNWIND tail(ms) AS m DELETE m",
    "CREATE CONSTRAINT meta_key IF NOT EXISTS FOR (m:Meta) REQUIRE m.key IS UNIQUE",
    # Unused since vector search scans per file; only cost writes
    "DROP INDEX chunk_embedding IF EXISTS",
    "CREATE FULLTEXT INDEX chunk_text IF NOT EXISTS FOR (c:Chunk) ON EACH [c.text]",
    "CREATE INDEX entity_key IF NOT EXISTS FOR (e:__Entity__) ON (e.file_id, e.key)",
    "CREATE INDEX chunk_file IF NOT EXISTS FOR (c:Chunk) ON (c.file_id)",
    "CREATE INDEX section_file IF NOT EXISTS FOR (s:Section) ON (s.file_id)",
    "CREATE INDEX turn_file IF NOT EXISTS FOR (t:Turn) ON (t.file_id)",
    "CREATE INDEX table_file IF NOT EXISTS FOR (e:TableExtraction) ON (e.file_id)",
    "CREATE INDEX doc_table_file IF NOT EXISTS FOR (t:DocTable) ON (t.file_id)",
    "CREATE FULLTEXT INDEX entity_name IF NOT EXISTS FOR (e:__Entity__) ON EACH [e.name]",
]

READ_MARKER = """
MERGE (m:Meta {key: 'embedding'})
ON CREATE SET m.model = $model, m.dim = $dim
RETURN m.model AS model, m.dim AS dim
"""

RESET_MESSAGE = (
    "Neo4j holds {chunks} chunks embedded with {old} ({old_dim} dims), but the config uses {new} ({new_dim} dims). "
    "Vectors from different models are not comparable, so search would silently return nonsense. "
    "Set the provider back, or re-ingest the documents after running in Neo4j: "
    "MATCH (c:Chunk) DETACH DELETE c; MATCH (m:Meta {{key: 'embedding'}}) DELETE m"
)


def check_embedding_model(g: Neo4jGraph) -> None:
    """Refuse to mix embeddings from different models, which a dimension check alone does not catch."""
    stored = g.query(READ_MARKER, {"model": settings.embed_model, "dim": settings.embed_dim})[0]
    if stored["model"] == settings.embed_model and stored["dim"] == settings.embed_dim:
        # A database from before the marker can still hold vectors of another size
        sample = g.query("MATCH (c:Chunk) WHERE c.embedding IS NOT NULL RETURN size(c.embedding) AS dim LIMIT 1")
        if sample and sample[0]["dim"] != settings.embed_dim:
            chunks = g.query("MATCH (c:Chunk) WHERE c.embedding IS NOT NULL RETURN count(c) AS n")[0]["n"]
            raise RuntimeError(RESET_MESSAGE.format(
                chunks=chunks, old="an unknown model", old_dim=sample[0]["dim"],
                new=settings.embed_model, new_dim=settings.embed_dim,
            ))
        return

    chunks = g.query("MATCH (c:Chunk) WHERE c.embedding IS NOT NULL RETURN count(c) AS n")[0]["n"]
    if chunks:
        raise RuntimeError(RESET_MESSAGE.format(
            chunks=chunks, old=stored["model"], old_dim=stored["dim"],
            new=settings.embed_model, new_dim=settings.embed_dim,
        ))

    g.query(
        "MATCH (m:Meta {key: 'embedding'}) SET m.model = $model, m.dim = $dim",
        {"model": settings.embed_model, "dim": settings.embed_dim},
    )


@lru_cache
def graph() -> Neo4jGraph:
    g = Neo4jGraph(
        url=settings.neo4j_uri,
        username=settings.neo4j_user,
        password=settings.neo4j_password,
        refresh_schema=False,
    )
    # Schema first, so the marker MERGE below runs under the meta_key constraint
    for statement in SCHEMA:
        g.query(statement)
    from app import model_settings
    model_settings.load(g)
    check_embedding_model(g)
    return g
