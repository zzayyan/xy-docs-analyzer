from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from langchain_core.documents import Document
from langchain_neo4j import LLMGraphTransformer

from app.config import settings
from app.db import graph
from app.models import llm

ALLOWED_NODES = ["Person", "Organization", "Location", "Concept", "Event", "Product", "Regulation", "Date"]

WRITE_ENTITIES = """
MATCH (c:Chunk {id: $chunk_id})
UNWIND $entities AS e
MERGE (n:__Entity__ {file_id: $file_id, key: e.key})
ON CREATE SET n.name = e.name, n.type = e.type
MERGE (c)-[:MENTIONS]->(n)
"""

# Relationship types come from the LLM and vary per chunk, so they are merged dynamically via APOC
WRITE_RELATIONSHIPS = """
UNWIND $relationships AS r
MATCH (s:__Entity__ {file_id: $file_id, key: r.source})
MATCH (t:__Entity__ {file_id: $file_id, key: r.target})
CALL apoc.merge.relationship(s, r.type, {}, {}, t, {}) YIELD rel
RETURN count(rel) AS written
"""


@lru_cache
def transformer() -> LLMGraphTransformer:
    # Spike on qwen3:14b: prompt-based extraction found ~2x more relations than tool calling, and ran faster
    return LLMGraphTransformer(llm=llm(), allowed_nodes=ALLOWED_NODES, ignore_tool_usage=True)


def entity_key(name: str) -> str:
    return " ".join(name.lower().split())


ATTEMPTS = 3


def extract_one(text: str):
    """One LLM call, no database access, so it is safe to run many at once. None when every attempt
    failed: the graph only helps retrieval, and the chunk stays findable through the outline and vector
    search, so one bad chunk is skipped rather than failing a whole Document after its conversion."""
    for _ in range(ATTEMPTS):
        try:
            [doc] = transformer().convert_to_graph_documents([Document(page_content=text)])
            return doc
        except Exception:
            pass
    return None


def extract_graph(file_id: str, chunks: list[dict], on_progress: Callable[[int, int], None] | None = None) -> int:
    """Extract entities and relationships per chunk and link each chunk to the entities it mentions.
    Returns how many chunks were skipped because extraction kept failing on them."""
    skipped = 0
    # Extraction is one HTTP call per chunk, so it parallelises; the writes stay on this thread because
    # concurrent MERGE on the same __Entity__ nodes deadlocks in Neo4j. map() keeps chunk order, and
    # consuming it inside the pool interleaves writes with extraction so progress moves while work runs.
    with ThreadPoolExecutor(max_workers=settings.llm_concurrency) as pool:
        extracted = pool.map(extract_one, [chunk["text"] for chunk in chunks])
        try:
            for done, (chunk, doc) in enumerate(zip(chunks, extracted), start=1):
                if doc is None:
                    skipped += 1
                else:
                    write_chunk_graph(file_id, chunk["id"], doc)
                if on_progress:
                    on_progress(done, len(chunks))
        finally:
            # A raise in the loop (the Document was deleted) cancels every chunk not yet started,
            # instead of the pool's exit waiting for all of them to run
            extracted.close()
    return skipped


def write_chunk_graph(file_id: str, chunk_id: str, doc) -> None:
    entities = {entity_key(n.id): {"key": entity_key(n.id), "name": n.id, "type": n.type} for n in doc.nodes}
    # Relationship endpoints are not always listed in doc.nodes
    for rel in doc.relationships:
        for node in (rel.source, rel.target):
            entities.setdefault(entity_key(node.id), {"key": entity_key(node.id), "name": node.id, "type": node.type})
    relationships = [
        {"source": entity_key(r.source.id), "target": entity_key(r.target.id), "type": r.type}
        for r in doc.relationships
    ]

    params = {"file_id": file_id, "chunk_id": chunk_id}
    graph().query(WRITE_ENTITIES, {**params, "entities": list(entities.values())})
    graph().query(WRITE_RELATIONSHIPS, {**params, "relationships": relationships})
