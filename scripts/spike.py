"""Milestone 0 spike: check Docling heading hierarchy and local KG extraction on a real document.

Usage: uv run python -m scripts.spike path/to/document.pdf [chunks_to_extract=5]
Needs only Ollama (no Neo4j).
"""
import sys
import time

from docling_core.types.doc.document import SectionHeaderItem, TitleItem
from langchain_core.documents import Document
from langchain_neo4j import LLMGraphTransformer

from app.config import settings
from app.ingest.convert import convert
from app.models import llm

ALLOWED_NODES = ["Person", "Organization", "Location", "Concept", "Event", "Product", "Regulation", "Date"]


def main(path: str, n_chunks: int) -> None:
    start = time.perf_counter()
    doc, tokens, chunks = convert(path)
    mode = "long" if tokens > settings.long_doc_tokens else "short"
    print(f"converted in {time.perf_counter() - start:.1f}s | tokens={tokens} | mode={mode} | chunks={len(chunks)}")

    print("\n# Headings")
    levels = []
    for item, _depth in doc.iterate_items():
        if isinstance(item, (TitleItem, SectionHeaderItem)):
            level = 0 if isinstance(item, TitleItem) else item.level
            levels.append(level)
            print(f"{'  ' * level}[{level}] {item.text[:90]}")
    print(f"distinct heading levels: {sorted(set(levels))} (one level = flat, numbering fallback needed)")

    docs = [Document(page_content=c["text"]) for c in chunks[:n_chunks]]
    for ignore_tool_usage in (False, True):
        print(f"\n# KG extraction, ignore_tool_usage={ignore_tool_usage}")
        transformer = LLMGraphTransformer(llm=llm(), allowed_nodes=ALLOWED_NODES, ignore_tool_usage=ignore_tool_usage)
        start = time.perf_counter()
        try:
            results = transformer.convert_to_graph_documents(docs)
        except Exception as exc:
            print(f"FAILED: {exc!r}")
            continue
        elapsed = time.perf_counter() - start
        print(f"{elapsed:.1f}s total, {elapsed / max(len(docs), 1):.1f}s per chunk")
        for i, result in enumerate(results):
            print(f"chunk {i}: {len(result.nodes)} nodes, {len(result.relationships)} relationships")
            for rel in result.relationships[:8]:
                print(f"  ({rel.source.id}:{rel.source.type}) -[{rel.type}]-> ({rel.target.id}:{rel.target.type})")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 5)
