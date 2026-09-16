import re

from app.db import graph
from app.models import embeddings

LUCENE_SPECIAL = re.compile(r'[+\-&|!(){}\[\]^"~*?:\\/]')

VECTOR_QUERY = """
CALL db.index.vector.queryNodes('chunk_embedding', $candidates, $vector) YIELD node, score
WHERE node.file_id = $file_id
RETURN node.id AS id, node.text AS text, node.pages AS pages, node.headings AS headings
LIMIT $k
"""

KEYWORD_QUERY = """
CALL db.index.fulltext.queryNodes('chunk_text', $text) YIELD node, score
WHERE node.file_id = $file_id
RETURN node.id AS id, node.text AS text, node.pages AS pages, node.headings AS headings
LIMIT $k
"""

# The vector index is global across all files; candidates are filtered by file_id after retrieval, so once
# several documents share the index a small candidate pool can return zero hits for the file being searched
MIN_CANDIDATES = 500


def search(file_id: str, question: str, k: int = 6) -> list[dict]:
    """Hybrid search over one file's chunks: vector + fulltext, merged with reciprocal rank fusion."""
    ranked_lists = [graph().query(VECTOR_QUERY, {
        "candidates": max(k * 10, MIN_CANDIDATES),
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
