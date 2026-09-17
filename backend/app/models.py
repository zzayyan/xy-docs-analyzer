from functools import lru_cache

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.config import settings


def _api_key(key: str, env_var: str) -> str:
    # Without this the failure surfaces as an opaque auth error from the server
    if not key:
        raise RuntimeError(f"{env_var} is required when the provider is 'openai'")
    return key


def llm(model: str | None = None) -> BaseChatModel:
    # A thin wrapper around the cached builder so every caller -- whether it passes a document's
    # chosen model, or nothing -- resolves to the same cache key for the default model, instead of
    # _llm(None) and _llm(settings.llm_model) building two equivalent clients.
    return _llm(model or settings.llm_model)


@lru_cache
def _llm(model: str) -> BaseChatModel:
    if settings.llm_provider == "openai":
        return ChatOpenAI(
            model=model,
            api_key=_api_key(settings.llm_api_key, "LLM_API_KEY"),
            base_url=settings.llm_base_url,
            temperature=0,
            # Qwen3.5 on vLLM spends every token on reasoning and leaves content empty until it stops
            reasoning_effort="none",
        )
    return ChatOllama(
        model=model,
        base_url=settings.llm_base_url,
        temperature=0,
        num_ctx=settings.llm_num_ctx,
        # Keeps qwen3 <think> output out of answers and extraction JSON
        reasoning=False,
    )


@lru_cache
def embeddings() -> Embeddings:
    if settings.embed_provider == "openai":
        return OpenAIEmbeddings(
            model=settings.embed_model,
            api_key=_api_key(settings.embed_api_key, "EMBED_API_KEY"),
            base_url=settings.embed_base_url,
            # Non-OpenAI models are not in tiktoken, so let the server do the token accounting
            check_embedding_ctx_length=False,
        )
    return OllamaEmbeddings(model=settings.embed_model, base_url=settings.embed_base_url)
