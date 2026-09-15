from functools import lru_cache

from langchain_neo4j import Neo4jGraph

from app.config import settings

SCHEMA = [
    "CREATE CONSTRAINT file_id IF NOT EXISTS FOR (f:File) REQUIRE f.id IS UNIQUE",
    "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT section_id IF NOT EXISTS FOR (s:Section) REQUIRE s.id IS UNIQUE",
    "CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS FOR (c:Chunk) ON c.embedding "
    f"OPTIONS {{indexConfig: {{`vector.dimensions`: {settings.embed_dim}, "
    "`vector.similarity_function`: 'cosine'}}",
    "CREATE FULLTEXT INDEX chunk_text IF NOT EXISTS FOR (c:Chunk) ON EACH [c.text]",
    "CREATE INDEX entity_key IF NOT EXISTS FOR (e:__Entity__) ON (e.file_id, e.key)",
    "CREATE FULLTEXT INDEX entity_name IF NOT EXISTS FOR (e:__Entity__) ON EACH [e.name]",
]


@lru_cache
def graph() -> Neo4jGraph:
    g = Neo4jGraph(
        url=settings.neo4j_uri,
        username=settings.neo4j_user,
        password=settings.neo4j_password,
        refresh_schema=False,
    )
    for statement in SCHEMA:
        g.query(statement)
    return g
