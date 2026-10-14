import re

from app.db import graph
from app.models import embeddings

LUCENE_SPECIAL = re.compile(r'[+\-&|!(){}\[\]^"~*?:\\/]')

# Exact scan of one file's chunks: the global index returns nearest chunks across every document, so a
# file's own could all miss the candidates.
# ponytail: full scan, fine up to MAX_PAGES (~800 chunks); filtered index (Neo4j 2025+ SEARCH) past that
VECTOR_QUERY = """
MATCH (node:Chunk {file_id: $file_id})
WITH node, vector.similarity.cosine(node.embedding, $vector) AS score
ORDER BY score DESC
LIMIT $k
RETURN node.id AS id, node.text AS text, node.pages AS pages, node.headings AS headings, node.regions AS regions
"""

KEYWORD_QUERY = """
CALL db.index.fulltext.queryNodes('chunk_text', $text) YIELD node, score
WHERE node.file_id = $file_id
RETURN node.id AS id, node.text AS text, node.pages AS pages, node.headings AS headings, node.regions AS regions
LIMIT $k
"""


def search(file_id: str, question: str, k: int = 6) -> list[dict]:
    """Vector + fulltext, merged with reciprocal rank fusion."""
    ranked_lists = [graph().query(VECTOR_QUERY, {
        "vector": embeddings().embed_query(question),
        "file_id": file_id,
        "k": k,
    })]

    # Lowercased: Lucene reads an uppercase AND/OR/NOT as an operator, and a dangling one is a parse error
    text = LUCENE_SPECIAL.sub(" ", question).strip().lower()
    if text:
        ranked_lists.append(graph().query(KEYWORD_QUERY, {"text": text, "file_id": file_id, "k": k}))

    scores: dict[str, float] = {}
    rows: dict[str, dict] = {}
    for ranked in ranked_lists:
        for rank, row in enumerate(ranked):
            scores[row["id"]] = scores.get(row["id"], 0.0) + 1 / (60 + rank)
            rows[row["id"]] = row
    return [rows[i] for i in sorted(scores, key=scores.get, reverse=True)[:k]]
