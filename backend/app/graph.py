import json
import operator
import re
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
    model: str | None  # the document's chosen LLM, or None for settings.llm_model
    history: list[dict]  # prior {question, answer} turns, oldest first
    search_query: str  # question rewritten standalone against history, for retrieval only
    retrieved: Annotated[list[dict], operator.add]  # parallel retrievers append here
    contexts: list[dict]  # deduplicated, budgeted input for generate
    answer: str


SYSTEM_PROMPT = (
    "You answer questions about a document using only the numbered context blocks. "
    "Cite blocks inline as [n]. If the context does not contain the answer, say so. "
    "Answer in the same language as the question."
)

CONTEXTUALIZE_SYSTEM_PROMPT = (
    "Rewrite the latest question as a standalone question that makes sense without the earlier "
    "conversation. Resolve pronouns and references like \"that\", \"the second one\", or \"the "
    "third one\" using the conversation history -- if the previous answer contains a numbered or "
    "bulleted list, an ordinal reference points at that specific item: pull its actual content "
    "into the rewrite, don't just describe it as \"the Nth item\". If the question is already "
    "standalone, return it unchanged. Reply with only the rewritten question, no explanation, no "
    "quotes.\n\n"
    "Example -- previous answer contains \"3. Structured content yields big gains\"; latest "
    "question is \"what about the third one?\" -- rewrite to: \"What does it mean that structured "
    "content yields big gains?\""
)

CITATION_MARKER = re.compile(r"\[\d+\]")


def strip_citations(text: str) -> str:
    """A prior turn's [n] markers are meaningless outside that turn -- the numbers are reassigned
    fresh every turn from whatever fuse() retrieves this time -- and are noise at best, actively
    misleading at worst (a small model can conflate an ordinal like "the third one" with a
    same-shaped "[3]" sitting right next to it in the history transcript)."""
    return CITATION_MARKER.sub("", text)

# Graph facts are compact and relational, so they go first; then section/vector chunks; then KG evidence chunks
SOURCE_PRIORITY = {"kg_facts": 0, "vector": 1, "tree": 1, "kg": 2}

# How many prior turns feed the follow-up rewrite and the final answer's own conversational
# memory. Not token-budgeted like fuse()'s context blocks -- a handful of turns is cheap relative
# to the document context, and capping by count is simpler than tracking two separate budgets.
MAX_HISTORY_TURNS = 6


def recent_history(state: State) -> list[dict]:
    return state.get("history", [])[-MAX_HISTORY_TURNS:]


def route(state: State) -> list[str]:
    # Long documents keep vector search too: tree search depends on the model picking the right section,
    # the graph only finds named entities, and a question about one clause or number can miss both
    return ["tree_search", "kg_retrieve", "vector_retrieve"] if state["mode"] == "long" else ["vector_retrieve"]


def contextualize(state: State) -> dict:
    """Resolve a follow-up question ("what about the second one?") into a standalone one before
    retrieval runs on it -- retrieval only ever sees the raw question text, so without this a
    follow-up that depends on the prior turn finds nothing relevant no matter how much history
    generate() is later given to work with."""
    history = recent_history(state)
    if not history:
        # First turn: nothing to resolve against, skip the extra LLM round trip entirely.
        return {"search_query": state["question"]}
    transcript = "\n".join(f"Q: {h['question']}\nA: {strip_citations(h['answer'])}" for h in history)
    message = llm(state.get("model")).invoke([
        ("system", CONTEXTUALIZE_SYSTEM_PROMPT),
        ("human", f"Conversation so far:\n{transcript}\n\nLatest question: {state['question']}"),
    ])
    rewritten = (message.content or "").strip()
    return {"search_query": rewritten or state["question"]}


def _contexts(rows: list[dict], source: str) -> list[dict]:
    """Tags each retrieved row with its source and decodes its regions -- a Neo4j property can't hold a
    list of maps, so c.regions travels as JSON the same way Turn.citations does."""
    return [{**row, "source": source, "regions": json.loads(row.get("regions") or "[]")} for row in rows]


def vector_retrieve(state: State) -> dict:
    query = state.get("search_query") or state["question"]
    return {"retrieved": _contexts(vector.search(state["doc_id"], query), "vector")}


def tree_retrieve(state: State) -> dict:
    query = state.get("search_query") or state["question"]
    chunks = tree_search.search(state["doc_id"], query, model=state.get("model"))
    return {"retrieved": _contexts(chunks, "tree")}


def kg_retrieve(state: State) -> dict:
    query = state.get("search_query") or state["question"]
    facts, chunks = kg.search(state["doc_id"], query, model=state.get("model"))
    retrieved = _contexts(chunks, "kg")
    if facts:
        text = "Knowledge graph facts:\n" + "\n".join(facts)
        retrieved.insert(0, {
            "id": "kg:facts", "text": text, "pages": [], "headings": [], "regions": [], "source": "kg_facts",
        })
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


def to_citations(contexts: list[dict]) -> list[dict]:
    """Citation entries for the frontend: includes chunk text so drill-down needs no extra lookup, and
    survives a chunk being deleted or re-ingested later (sent live, and persisted with the Turn)."""
    return [
        {
            "n": n,
            "chunk_id": c["id"],
            "pages": c["pages"],
            "headings": c.get("headings") or [],
            "regions": c.get("regions") or [],
            "source": c["source"],
            "text": c["text"],
        }
        for n, c in enumerate(contexts, start=1)
    ]


def generate(state: State) -> dict:
    contexts = state.get("contexts", [])
    blocks = "\n\n".join(
        f"[{n}] (pages: {c['pages'] or '-'})\n{c['text']}" for n, c in enumerate(contexts, start=1)
    )
    # Prior turns as real conversational messages (not text stuffed into the prompt), so pronoun
    # references, tone, and "you already told me X" carry over the way a chat is expected to.
    history_messages = [
        msg for h in recent_history(state) for msg in (("human", h["question"]), ("ai", strip_citations(h["answer"])))
    ]
    message = llm(state.get("model")).invoke([
        ("system", SYSTEM_PROMPT),
        *history_messages,
        ("human", f"Context:\n{blocks}\n\nQuestion: {state['question']}"),
    ])
    return {"answer": message.content}


builder = StateGraph(State)
builder.add_node("contextualize", contextualize)
builder.add_node("vector_retrieve", vector_retrieve)
builder.add_node("tree_search", tree_retrieve)
builder.add_node("kg_retrieve", kg_retrieve)
builder.add_node("fuse", fuse)
builder.add_node("generate", generate)
builder.add_edge(START, "contextualize")
builder.add_conditional_edges("contextualize", route, ["vector_retrieve", "tree_search", "kg_retrieve"])
builder.add_edge("vector_retrieve", "fuse")
builder.add_edge(["tree_search", "kg_retrieve"], "fuse")  # waits for both parallel branches
builder.add_edge("fuse", "generate")
builder.add_edge("generate", END)
workflow = builder.compile()
