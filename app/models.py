from functools import lru_cache

from langchain_ollama import ChatOllama, OllamaEmbeddings

from app.config import settings


@lru_cache
def llm() -> ChatOllama:
    return ChatOllama(
        model=settings.llm_model,
        base_url=settings.ollama_base_url,
        temperature=0,
        # Ollama's default context is small and truncates silently; outlines and fused contexts need more
        num_ctx=settings.llm_num_ctx,
        # Keeps qwen3 <think> output out of answers and extraction JSON
        reasoning=False,
    )


@lru_cache
def embeddings() -> OllamaEmbeddings:
    return OllamaEmbeddings(model=settings.embed_model, base_url=settings.ollama_base_url)
