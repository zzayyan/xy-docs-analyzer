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
from app.retrieval import kg, tree_search, vector


class State(TypedDict, total=False):
    question: str
    doc_id: str
    mode: str  # "short" | "long"
    model: str | None  # the document's chosen LLM, or None for settings.llm_model
    history: list[dict]  # prior {question, answer} turns, oldest first
    search_queries: list[str]  # the question as 1-3 standalone search queries, for retrieval only
    retrieved: Annotated[list[dict], operator.add]  # parallel retrievers append here
    contexts: list[dict]  # deduplicated, budgeted input for generate
    answer: str


SYSTEM_PROMPT = (
    "You answer questions about a document using only the numbered context blocks. "
    "Cite blocks inline as [n]. If the context does not contain the answer, say so. "
    "Answer in the same language as the question."
)

MAX_SUB_QUERIES = 3

CONTEXTUALIZE_SYSTEM_PROMPT = (
    "You turn the latest question into search queries for a document. Write every query in the SAME "
    "language as the latest question: an English question gives English queries, an Indonesian "
    "question gives Indonesian queries, whatever language the examples below are in. Follow these "
    "rules in order.\n"
    "1. Make it standalone, so it makes sense without the earlier conversation: resolve pronouns and "
    "references like \"that\", \"the second one\", or \"the third one\" using the conversation history "
    "-- if the previous answer contains a numbered or bulleted list, an ordinal reference points at "
    "that specific item: put its actual content in the query, don't just say \"the Nth item\".\n"
    "2. A comparison ALWAYS becomes one question per thing being compared. That is any question with "
    "\"bandingkan\", \"perbandingan\", \"perbedaan\", \"beda\", \"lebih ... dari\", \"compare\", "
    "\"comparison\", \"difference\", \"versus\", \"vs\", or \"X or Y, which\". Each question names "
    "exactly ONE of the things and asks ALL the aspects the user asked about for that one thing, "
    "together in one question: split by thing, never by aspect. The "
    "comparison word never appears in them: \"perbedaan X\" or \"compare X\" is not a question about X. "
    "When no aspect is named (\"apa perbedaan X dan Y\", \"bandingkan keduanya\"), ask what the "
    "document says about each one.\n"
    "3. A question about several unrelated topics joined by \"dan\", \"serta\", \"and\" also becomes "
    "one question per topic.\n"
    f"4. Never more than {MAX_SUB_QUERIES} questions. A question about one thing stays one question, "
    "unchanged if it is already standalone.\n"
    "5. Keep the language of the question. Never answer it, add facts, or add topics it does not ask "
    "about.\n\n"
    "Examples:\n"
    "- History has \"3. Structured content yields big gains\"; \"what about the third one?\" -> "
    "[\"What does it mean that structured content yields big gains?\"]\n"
    "- \"Bandingkan akurasi dan kecepatan model A dengan model B\" -> [\"Berapa akurasi dan kecepatan "
    "model A?\", \"Berapa akurasi dan kecepatan model B?\"]\n"
    "- \"Apa perbedaan Perda 13/2018 dan Perda 3/2023?\" -> [\"Apa yang dijelaskan tentang Perda "
    "13/2018?\", \"Apa yang dijelaskan tentang Perda 3/2023?\"]\n"
    "- History lists \"1. Paket A 2. Paket B\"; \"bandingkan keduanya\" -> [\"Apa yang dijelaskan "
    "tentang Paket A?\", \"Apa yang dijelaskan tentang Paket B?\"]\n"
    "- \"Mana yang lebih murah, paket A atau paket B?\" -> [\"Berapa harga paket A?\", \"Berapa harga "
    "paket B?\"]\n"
    "- \"Compare the cost and duration of plan A and plan B\" -> [\"What are the cost and duration of "
    "plan A?\", \"What are the cost and duration of plan B?\"]\n"
    "- \"Compare the penalties for the contractor vs the client\" -> [\"What penalties apply to the "
    "contractor?\", \"What penalties apply to the client?\"]\n"
    "- \"Siapa kontraktornya dan kapan tenggatnya?\" -> [\"Siapa kontraktornya?\", \"Kapan "
    "tenggatnya?\"]\n"
    "- \"Berapa nilai kontrak proyek ini?\" -> [\"Berapa nilai kontrak proyek ini?\"]"
)


class SearchQueries(BaseModel):
    queries: list[str] = Field(description=f"1 to {MAX_SUB_QUERIES} standalone search questions")

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
    """Turn the question into the queries retrieval runs on, in one call:

    - a follow-up ("what about the second one?") becomes standalone -- retrieval only ever sees the
      query text, so without this it finds nothing relevant however much history generate() gets;
    - a compound question ("compare the value and deadline of project A and project B") becomes one
      query per thing it asks about, so each half gets its own search instead of one blurred query.

    Runs on every question, first turn included, since compound questions come first as often as not.
    Any failure falls back to the question as asked: a worse search, never a failed answer."""
    history = recent_history(state)
    transcript = "\n".join(f"Q: {h['question']}\nA: {strip_citations(h['answer'])}" for h in history)
    conversation = f"Conversation so far:\n{transcript}\n\n" if history else ""
    try:
        found = llm(state.get("model")).with_structured_output(SearchQueries).invoke([
            ("system", CONTEXTUALIZE_SYSTEM_PROMPT),
            ("human", f"{conversation}Latest question: {state['question']}"),
        ])
        queries = [q.strip() for q in found.queries if q and q.strip()]
    except Exception:
        queries = []
    queries = list(dict.fromkeys(queries))
    # More than the cap means it split by aspect too ("precision of A", "recall of A", "precision of B",
    # ...), and cutting the list would silently drop one of the things compared. The question as asked
    # still covers all of them, just less sharply, so it is the safer query.
    if len(queries) > MAX_SUB_QUERIES:
        queries = []
    return {"search_queries": queries or [state["question"]]}


def search_queries(state: State) -> list[str]:
    return state.get("search_queries") or [state["question"]]


def _contexts(rows: list[dict], source: str) -> list[dict]:
    """Tags each retrieved row with its source and decodes its regions -- a Neo4j property can't hold a
    list of maps, so c.regions travels as JSON the same way Turn.citations does."""
    return [{**row, "source": source, "regions": json.loads(row.get("regions") or "[]")} for row in rows]


def vector_retrieve(state: State) -> dict:
    """One hybrid search per query (no model call, so cheap), interleaved best-first: fuse() keeps
    blocks in this order until the token budget runs out, so every sub-question gets its top hits in
    before any gets its tail."""
    per_query = [vector.search(state["doc_id"], q) for q in search_queries(state)]
    interleaved = [row for rank in zip_longest(*per_query) for row in rank if row is not None]
    return {"retrieved": _contexts(interleaved, "vector")}


def tree_retrieve(state: State) -> dict:
    # One model call for every sub-question: the outline is read once and sections picked for each
    query = "\n".join(search_queries(state))
    chunks = tree_search.search(state["doc_id"], query, model=state.get("model"))
    return {"retrieved": _contexts(chunks, "tree")}


def kg_retrieve(state: State) -> dict:
    # One entity extraction over every sub-question, rather than one call each
    query = "\n".join(search_queries(state))
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
