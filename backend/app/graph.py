import json
import operator
import re
from itertools import zip_longest
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.config import settings
from app.ingest.convert import tokenizer
from app.models import llm
from app.prompts import chat as prompts
from app.retrieval import kg, table, tree_search, vector


class State(TypedDict, total=False):
    question: str
    doc_id: str
    mode: str  # "short" | "long"
    model: str | None
    history: list[dict]
    language: str | None
    spreadsheet: bool  # XLSX or CSV: table_query computes over its rows
    search_queries: list[str]
    retrieved: Annotated[list[dict], operator.add]  # parallel retrievers append here
    contexts: list[dict]
    answer: str


MAX_SUB_QUERIES = 3


def contextualize_prompt(language: str | None) -> str:
    if language:
        return prompts.CONTEXTUALIZE.format(
            language_rule=prompts.DOCUMENT_LANGUAGE.format(language=language), keep_language=prompts.KEEP_DOCUMENT_LANGUAGE,
            max_queries=MAX_SUB_QUERIES,
        )
    return prompts.CONTEXTUALIZE.format(
        language_rule=prompts.QUESTION_LANGUAGE, keep_language=prompts.KEEP_QUESTION_LANGUAGE,
        max_queries=MAX_SUB_QUERIES,
    )


class SearchQueries(BaseModel):
    queries: list[str] = Field(description=f"1 to {MAX_SUB_QUERIES} standalone search questions")

# "[3]", and the grouped forms models also write: "[4, 5]", "[4;5]", "[4-6]"
CITATION_MARKER = re.compile(r"\[\d+(?:\s*[,;–-]\s*\d+)*\]")


def strip_citations(text: str) -> str:
    # A prior turn's [n] numbers mean nothing now, and a small model confuses "the third one" with "[3]"
    return CITATION_MARKER.sub("", text)

SOURCE_PRIORITY = {"table": 0, "kg_facts": 1, "vector": 2, "tree": 2, "kg": 3}

MAX_HISTORY_TURNS = 6


def recent_history(state: State) -> list[dict]:
    return state.get("history", [])[-MAX_HISTORY_TURNS:]


def route(state: State) -> list[str]:
    # Long documents keep vector search: a question about one clause or number can miss tree and graph both
    nodes = ["tree_search", "kg_retrieve", "vector_retrieve"] if state["mode"] == "long" else ["vector_retrieve"]
    return nodes + ["table_query"] if state.get("spreadsheet") else nodes


def contextualize(state: State) -> dict:
    """One call that makes a follow-up standalone, splits a compound question into one query per thing,
    and translates to the Document Language. Any failure falls back to the question as asked."""
    history = recent_history(state)
    transcript = "\n".join(f"Q: {h['question']}\nA: {strip_citations(h['answer'])}" for h in history)
    conversation = f"Conversation so far:\n{transcript}\n\n" if history else ""
    # Repeated after the question: from the system prompt alone, small models followed the examples' language
    language = state.get("language")
    reminder = f"\n\nWrite the queries in {language}." if language else ""
    try:
        found = llm(state.get("model")).with_structured_output(SearchQueries).invoke([
            ("system", contextualize_prompt(language)),
            ("human", f"{conversation}Latest question: {state['question']}{reminder}"),
        ])
        queries = [q.strip() for q in found.queries if q and q.strip()]
    except Exception:
        queries = []
    queries = list(dict.fromkeys(queries))
    # Over the cap means it split by aspect too; truncating would silently drop a compared thing
    if len(queries) > MAX_SUB_QUERIES:
        queries = []
    return {"search_queries": queries or [state["question"]]}


def search_queries(state: State) -> list[str]:
    return state.get("search_queries") or [state["question"]]


def _contexts(rows: list[dict], source: str) -> list[dict]:
    return [{**row, "source": source, "regions": json.loads(row.get("regions") or "[]")} for row in rows]


def vector_retrieve(state: State) -> dict:
    # Interleaved best-first, so every sub-question's top hits fit the budget before any one's tail
    per_query = [vector.search(state["doc_id"], q) for q in search_queries(state)]
    interleaved = [row for rank in zip_longest(*per_query) for row in rank if row is not None]
    return {"retrieved": _contexts(interleaved, "vector")}


def tree_retrieve(state: State) -> dict:
    query = "\n".join(search_queries(state))
    chunks = tree_search.search(state["doc_id"], query, model=state.get("model"))
    return {"retrieved": _contexts(chunks, "tree")}


def kg_retrieve(state: State) -> dict:
    query = "\n".join(search_queries(state))
    facts, chunks = kg.search(state["doc_id"], query, model=state.get("model"))
    retrieved = _contexts(chunks, "kg")
    if facts:
        text = "Knowledge graph facts:\n" + "\n".join(facts)
        retrieved.insert(0, {
            "id": "kg:facts", "text": text, "pages": [], "headings": [], "regions": [], "source": "kg_facts",
        })
    return {"retrieved": retrieved}


def table_retrieve(state: State) -> dict:
    query = "\n".join(search_queries(state))
    return {"retrieved": table.search(state["doc_id"], query, model=state.get("model"))}


def fuse(state: State) -> dict:
    seen: set[str] = set()
    contexts, used_tokens = [], 0
    # sorted() is stable, so each retriever's own ranking is kept within a priority level
    for item in sorted(state.get("retrieved", []), key=lambda c: SOURCE_PRIORITY[c["source"]]):
        if item["id"] in seen:
            continue
        size = tokenizer().count_tokens(item["text"])
        if used_tokens + size > settings.context_token_budget:
            continue
        seen.add(item["id"])
        contexts.append(item)
        used_tokens += size
    return {"contexts": contexts}


def to_citations(contexts: list[dict]) -> list[dict]:
    return [
        {
            "n": n,
            "chunk_id": c["id"],
            "pages": c["pages"],
            "headings": c.get("headings") or [],
            "regions": c.get("regions") or [],
            "refs": c.get("refs") or [],
            "source": c["source"],
            "text": c["text"],
        }
        for n, c in enumerate(contexts, start=1)
    ]


# Without it a small model redoes the arithmetic from the rows it can see, and gets it wrong
COMPUTED = "(computed by the system over the whole sheet; state these numbers as given)"


def block_header(context: dict) -> str:
    return COMPUTED if context.get("source") == "table" else f"(pages: {context['pages'] or '-'})"


def generate(state: State) -> dict:
    contexts = state.get("contexts", [])
    blocks = "\n\n".join(f"[{n}] {block_header(c)}\n{c['text']}" for n, c in enumerate(contexts, start=1))
    history_messages = [
        msg for h in recent_history(state) for msg in (("human", h["question"]), ("ai", strip_citations(h["answer"])))
    ]
    message = llm(state.get("model")).invoke([
        ("system", prompts.ANSWER),
        *history_messages,
        ("human", f"Context:\n{blocks}\n\nQuestion: {state['question']}"),
    ])
    return {"answer": message.content}


builder = StateGraph(State)
builder.add_node("contextualize", contextualize)
builder.add_node("vector_retrieve", vector_retrieve)
builder.add_node("tree_search", tree_retrieve)
builder.add_node("kg_retrieve", kg_retrieve)
builder.add_node("table_query", table_retrieve)
builder.add_node("fuse", fuse)
builder.add_node("generate", generate)
builder.add_edge(START, "contextualize")
builder.add_conditional_edges("contextualize", route, ["vector_retrieve", "tree_search", "kg_retrieve", "table_query"])
builder.add_edge("vector_retrieve", "fuse")
builder.add_edge("table_query", "fuse")
builder.add_edge(["tree_search", "kg_retrieve"], "fuse")
builder.add_edge("fuse", "generate")
builder.add_edge("generate", END)
workflow = builder.compile()
