from functools import lru_cache

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.config import settings


# A hung model server would otherwise hold an ingest or a table run at the same step forever. Long enough
# for the slowest honest call measured (a runaway chunk capped at EXTRACT_MAX_TOKENS).
LLM_TIMEOUT_S = 300


def _api_key(key: str, env_var: str) -> str:
    # Without this the failure surfaces as an opaque auth error from the server
    if not key:
        raise RuntimeError(f"{env_var} is required when the provider is 'openai'")
    return key


def llm(model: str | None = None, *, temperature: float = 0.0, max_tokens: int | None = None) -> BaseChatModel:
    # A thin wrapper around the cached builder so every caller -- whether it passes a document's
    # chosen model, or nothing -- resolves to the same cache key for the default model, instead of
    # _llm(None) and _llm(settings.llm_model) building two equivalent clients.
    #
    # temperature and max_tokens are set on the client, not bound onto it afterwards: a kwarg bound
    # with .bind() is dropped by with_structured_output(), which silently left an intended output cap
    # with no effect (measured: the capped call still ran to 15968 tokens).
    #
    # A document keeps the model it was last asked with; once Settings no longer offers that model
    # (another server, say), it falls back to the default instead of failing every call.
    if model not in settings.available_llm_models():
        model = settings.llm_model
    return _llm(model, temperature, max_tokens)


def chat_model(
    provider: str, base_url: str, api_key: str, model: str, *, temperature: float = 0.0,
    max_tokens: int | None = None, reasoning_effort: str | None = None, key_name: str = "LLM_API_KEY",
    timeout: float = LLM_TIMEOUT_S,
) -> BaseChatModel:
    """A client for any configured endpoint, uncached: Settings' connection test builds one from values
    that are not saved yet."""
    if provider == "openai":
        return ChatOpenAI(
            model=model,
            api_key=_api_key(api_key, key_name),
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            # Only when configured: Qwen3.5 on vLLM needs "none" or it spends every token on reasoning and
            # leaves content empty, while OpenAI itself rejects the parameter on non-reasoning models
            **({"reasoning_effort": reasoning_effort} if reasoning_effort else {}),
        )
    return ChatOllama(
        model=model,
        base_url=base_url,
        temperature=temperature,
        # Ollama's own name for a cap on the output; -1 is its default "no cap"
        num_predict=max_tokens or -1,
        num_ctx=settings.llm_num_ctx,
        client_kwargs={"timeout": timeout},
        # Keeps qwen3 <think> output out of answers and extraction JSON
        reasoning=False,
    )


# Cleared by app/model_settings.py whenever Settings change the endpoint
@lru_cache
def _llm(model: str, temperature: float = 0.0, max_tokens: int | None = None) -> BaseChatModel:
    return chat_model(
        settings.llm_provider, settings.llm_base_url, settings.llm_api_key, model,
        temperature=temperature, max_tokens=max_tokens, reasoning_effort=settings.llm_reasoning_effort,
    )


@lru_cache
def table_llm(temperature: float = 0.0, max_tokens: int | None = None) -> BaseChatModel:
    """Table Extraction's own model (TABLE_LLM_* in config), always an OpenAI-compatible endpoint."""
    return chat_model(
        "openai", settings.table_llm_base_url, settings.table_llm_api_key, settings.table_llm_model,
        temperature=temperature, max_tokens=max_tokens, key_name="TABLE_LLM_API_KEY",
    )


def embedding_model(provider: str, base_url: str, api_key: str, model: str) -> Embeddings:
    """Uncached, like chat_model: a re-index and the connection test embed with values not in use yet."""
    if provider == "openai":
        return OpenAIEmbeddings(
            model=model,
            api_key=_api_key(api_key, "EMBED_API_KEY"),
            base_url=base_url,
            # Non-OpenAI models are not in tiktoken, so let the server do the token accounting
            check_embedding_ctx_length=False,
        )
    return OllamaEmbeddings(model=model, base_url=base_url)


@lru_cache
def embeddings() -> Embeddings:
    return embedding_model(settings.embed_provider, settings.embed_base_url, settings.embed_api_key, settings.embed_model)
