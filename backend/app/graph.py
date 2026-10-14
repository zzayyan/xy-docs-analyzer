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
    model: str | None
    history: list[dict]
    language: str | None
    search_queries: list[str]
    retrieved: Annotated[list[dict], operator.add]  # parallel retrievers append here
    contexts: list[dict]
    answer: str


SYSTEM_PROMPT = (
    "You answer questions about a document using only the numbered context blocks. "
    "Cite blocks inline as [n]. If the context does not contain the answer, say so. "
    "Answer in the same language as the question."
)

MAX_SUB_QUERIES = 3

# Queries go in the document's language when known: fulltext, outline and entity names only match the
# document's own words (only the embeddings are multilingual)
QUESTION_LANGUAGE = (
    "Write every query in the SAME language as the latest question: an English question gives English "
    "queries, an Indonesian question gives Indonesian queries, whatever language the examples below are in."
)
DOCUMENT_LANGUAGE = (
    "The document is written in {language}. Write every query in {language}, translating the question when "
    "it is asked in another language, whatever language the examples below are in. Keep names, numbers and "
    "terms the question quotes exactly as written."
)
KEEP_QUESTION_LANGUAGE = "Keep the language of the question. "
KEEP_DOCUMENT_LANGUAGE = "Keep the meaning of the question. "

CONTEXTUALIZE_SYSTEM_PROMPT = (
    "You turn the latest question into search queries for a document. {language_rule} Follow these "
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
    "5. {keep_language}Never answer it, add facts, or add topics it does not ask "
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


def contextualize_prompt(language: str | None) -> str:
    if language:
        return CONTEXTUALIZE_SYSTEM_PROMPT.format(
            language_rule=DOCUMENT_LANGUAGE.format(language=language), keep_language=KEEP_DOCUMENT_LANGUAGE,
        )
    return CONTEXTUALIZE_SYSTEM_PROMPT.format(language_rule=QUESTION_LANGUAGE, keep_language=KEEP_QUESTION_LANGUAGE)


class SearchQueries(BaseModel):
    queries: list[str] = Field(description=f"1 to {MAX_SUB_QUERIES} standalone search questions")

# "[3]", and the grouped forms models also write: "[4, 5]", "[4;5]", "[4-6]"
CITATION_MARKER = re.compile(r"\[\d+(?:\s*[,;–-]\s*\d+)*\]")


def strip_citations(text: str) -> str:
    # A prior turn's [n] numbers mean nothing now, and a small model confuses "the third one" with "[3]"
    return CITATION_MARKER.sub("", text)

SOURCE_PRIORITY = {"kg_facts": 0, "vector": 1, "tree": 1, "kg": 2}

MAX_HISTORY_TURNS = 6


def recent_history(state: State) -> list[dict]:
    return state.get("history", [])[-MAX_HISTORY_TURNS:]


def route(state: State) -> list[str]:
    # Long documents keep vector search: a question about one clause or number can miss tree and graph both
    return ["tree_search", "kg_retrieve", "vector_retrieve"] if state["mode"] == "long" else ["vector_retrieve"]


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
builder.add_edge(["tree_search", "kg_retrieve"], "fuse")
builder.add_edge("fuse", "generate")
builder.add_edge("generate", END)
workflow = builder.compile()
