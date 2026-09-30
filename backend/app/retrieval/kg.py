from pydantic import BaseModel, Field

from app.db import graph
from app.models import llm
from app.retrieval.vector import LUCENE_SPECIAL

MATCHES_PER_NAME = 2

ENTITY_LOOKUP = """
UNWIND $names AS name
CALL db.index.fulltext.queryNodes('entity_name', name) YIELD node, score
WHERE node.file_id = $file_id
WITH name, node ORDER BY score DESC
WITH name, collect(node)[..$per_name] AS nodes
UNWIND nodes AS node
RETURN collect(DISTINCT node.key) AS keys
"""

# Relationship types vary between chunks (SERVES_ROUTE vs SERVES_ROUTE_TO), so traverse any type between entities
TRIPLES_QUERY = """
MATCH (e:__Entity__ {file_id: $file_id}) WHERE e.key IN $keys
MATCH p = (e)-[*1..2]-(:__Entity__)
WHERE all(n IN nodes(p) WHERE n:__Entity__)
UNWIND relationships(p) AS r
WITH r, min(length(p)) AS hops
ORDER BY hops
LIMIT $limit
RETURN startNode(r).name AS source, type(r) AS type, endNode(r).name AS target
"""

EVIDENCE_QUERY = """
MATCH (c:Chunk {file_id: $file_id})-[:MENTIONS]->(e:__Entity__)
WHERE e.key IN $keys
WITH c, count(DISTINCT e) AS hits
RETURN c.id AS id, c.text AS text, c.pages AS pages, c.headings AS headings, c.regions AS regions
ORDER BY hits DESC, c.idx
LIMIT $k
"""

SYSTEM_PROMPT = (
    "List the named things in the question: people, organizations, places, products, regulations, events, "
    "or key concepts. Copy each name as written. Return an empty list if there are none."
)


class QuestionEntities(BaseModel):
    names: list[str] = Field(description="Entity names mentioned in the question")


def search(
    file_id: str, question: str, k: int = 6, triple_limit: int = 30, model: str | None = None
) -> tuple[list[str], list[dict]]:
    """Return (graph facts as text lines, chunks that mention the matched entities)."""
    extracted = llm(model).with_structured_output(QuestionEntities).invoke([("system", SYSTEM_PROMPT), ("human", question)])
    # Lowercased so an uppercase AND/OR/NOT inside a name is a word, not a Lucene operator
    names = [name for name in (LUCENE_SPECIAL.sub(" ", n).strip().lower() for n in extracted.names) if name]
    if not names:
        return [], []

    [row] = graph().query(ENTITY_LOOKUP, {"names": names, "file_id": file_id, "per_name": MATCHES_PER_NAME})
    keys = row["keys"]
    if not keys:
        return [], []

    params = {"file_id": file_id, "keys": keys}
    triples = graph().query(TRIPLES_QUERY, {**params, "limit": triple_limit})
    facts = [f"({t['source']}) -[{t['type']}]-> ({t['target']})" for t in triples]
    return facts, graph().query(EVIDENCE_QUERY, {**params, "k": k})
