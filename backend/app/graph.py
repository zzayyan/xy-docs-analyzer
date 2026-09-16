import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.ingest.convert import tokenizer
from app.models import llm
from app.retrieval import kg, tree_search, vector


class State(TypedDict, total=False):
    question: str
    doc_id: str
    mode: str  # "short" | "long"
    retrieved: Annotated[list[dict], operator.add]  # parallel retrievers append here
    contexts: list[dict]  # deduplicated, budgeted input for generate
    answer: str
    citations: list[dict]


SYSTEM_PROMPT = (
    "You answer questions about a document using only the numbered context blocks. "
    "Cite blocks inline as [n]. If the context does not contain the answer, say so. "
    "Answer in the same language as the question."
)

# Graph facts are compact and relational, so they go first; then section/vector chunks; then KG evidence chunks
SOURCE_PRIORITY = {"kg_facts": 0, "vector": 1, "tree": 1, "kg": 2}


def route(state: State) -> list[str]:
    return ["tree_search", "kg_retrieve"] if state["mode"] == "long" else ["vector_retrieve"]


def vector_retrieve(state: State) -> dict:
    return {"retrieved": [{**c, "source": "vector"} for c in vector.search(state["doc_id"], state["question"])]}


def tree_retrieve(state: State) -> dict:
    return {"retrieved": [{**c, "source": "tree"} for c in tree_search.search(state["doc_id"], state["question"])]}


def kg_retrieve(state: State) -> dict:
    facts, chunks = kg.search(state["doc_id"], state["question"])
    retrieved = [{**c, "source": "kg"} for c in chunks]
    if facts:
        text = "Knowledge graph facts:\n" + "\n".join(facts)
        retrieved.insert(0, {"id": "kg:facts", "text": text, "pages": [], "source": "kg_facts"})
    return {"retrieved": retrieved}


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


def generate(state: State) -> dict:
    contexts = state.get("contexts", [])
    blocks = "\n\n".join(
        f"[{n}] (pages: {c['pages'] or '-'})\n{c['text']}" for n, c in enumerate(contexts, start=1)
    )
    message = llm().invoke([
        ("system", SYSTEM_PROMPT),
        ("human", f"Context:\n{blocks}\n\nQuestion: {state['question']}"),
    ])
    citations = [
        {"n": n, "chunk_id": c["id"], "pages": c["pages"], "source": c["source"]}
        for n, c in enumerate(contexts, start=1)
    ]
    return {"answer": message.content, "citations": citations}


builder = StateGraph(State)
builder.add_node("vector_retrieve", vector_retrieve)
builder.add_node("tree_search", tree_retrieve)
builder.add_node("kg_retrieve", kg_retrieve)
builder.add_node("fuse", fuse)
builder.add_node("generate", generate)
builder.add_conditional_edges(START, route, ["vector_retrieve", "tree_search", "kg_retrieve"])
builder.add_edge("vector_retrieve", "fuse")
builder.add_edge(["tree_search", "kg_retrieve"], "fuse")  # waits for both parallel branches
builder.add_edge("fuse", "generate")
builder.add_edge("generate", END)
workflow = builder.compile()
