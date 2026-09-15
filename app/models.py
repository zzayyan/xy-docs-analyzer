from functools import lru_cache

from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.config import settings


@lru_cache
def llm():
    if settings.provider == "openrouter":
        return ChatOpenAI(
            model=settings.openrouter_llm_model,
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            temperature=0,
        )
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
def embeddings():
    if settings.provider == "openrouter":
        return OpenAIEmbeddings(
            model=settings.openrouter_embed_model,
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            check_embedding_ctx_length=False,
        )
    return OllamaEmbeddings(model=settings.embed_model, base_url=settings.ollama_base_url)
