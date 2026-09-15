from collections.abc import Callable
from functools import lru_cache

from langchain_core.documents import Document
from langchain_neo4j import LLMGraphTransformer

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


def extract_graph(file_id: str, chunks: list[dict], on_progress: Callable[[int, int], None] | None = None) -> None:
    """Extract entities and relationships per chunk and link each chunk to the entities it mentions."""
    # ponytail: one LLM call per chunk, sequential; use aconvert_to_graph_documents with a semaphore if ingest is too slow
    for done, chunk in enumerate(chunks, start=1):
        [doc] = transformer().convert_to_graph_documents([Document(page_content=chunk["text"])])

        entities = {entity_key(n.id): {"key": entity_key(n.id), "name": n.id, "type": n.type} for n in doc.nodes}
        # Relationship endpoints are not always listed in doc.nodes
        for rel in doc.relationships:
            for node in (rel.source, rel.target):
                entities.setdefault(entity_key(node.id), {"key": entity_key(node.id), "name": node.id, "type": node.type})
        relationships = [
            {"source": entity_key(r.source.id), "target": entity_key(r.target.id), "type": r.type}
            for r in doc.relationships
        ]

        params = {"file_id": file_id, "chunk_id": chunk["id"]}
        graph().query(WRITE_ENTITIES, {**params, "entities": list(entities.values())})
        graph().query(WRITE_RELATIONSHIPS, {**params, "relationships": relationships})
        if on_progress:
            on_progress(done, len(chunks))
