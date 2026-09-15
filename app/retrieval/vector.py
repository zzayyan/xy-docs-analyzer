import re

from app.db import graph
from app.models import embeddings

LUCENE_SPECIAL = re.compile(r'[+\-&|!(){}\[\]^"~*?:\\/]')

VECTOR_QUERY = """
CALL db.index.vector.queryNodes('chunk_embedding', $candidates, $vector) YIELD node, score
WHERE node.file_id = $file_id
RETURN node.id AS id, node.text AS text, node.pages AS pages
LIMIT $k
"""

KEYWORD_QUERY = """
CALL db.index.fulltext.queryNodes('chunk_text', $text) YIELD node, score
WHERE node.file_id = $file_id
RETURN node.id AS id, node.text AS text, node.pages AS pages
LIMIT $k
"""


def search(file_id: str, question: str, k: int = 6) -> list[dict]:
    """Hybrid search over one file's chunks: vector + fulltext, merged with reciprocal rank fusion."""
    # ponytail: vector index is global, filtered after top-N; raise candidates or use
    # Neo4j 2025+ filtered vector search once many files share the index
    ranked_lists = [graph().query(VECTOR_QUERY, {
        "candidates": k * 10,
        "vector": embeddings().embed_query(question),
        "file_id": file_id,
        "k": k,
    })]

    text = LUCENE_SPECIAL.sub(" ", question).strip()
    if text:
        ranked_lists.append(graph().query(KEYWORD_QUERY, {"text": text, "file_id": file_id, "k": k}))

    scores: dict[str, float] = {}
    rows: dict[str, dict] = {}
    for ranked in ranked_lists:
        for rank, row in enumerate(ranked):
            scores[row["id"]] = scores.get(row["id"], 0.0) + 1 / (60 + rank)
            rows[row["id"]] = row
    return [rows[i] for i in sorted(scores, key=scores.get, reverse=True)[:k]]
