from functools import lru_cache

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.config import settings


# Covers the slowest measured honest call; a hung server would otherwise stall a run forever
LLM_TIMEOUT_S = 300


def _api_key(key: str, env_var: str) -> str:
    if not key:
        raise RuntimeError(f"{env_var} is required when the provider is 'openai'")
    return key


def llm(model: str | None = None, *, temperature: float = 0.0, max_tokens: int | None = None) -> BaseChatModel:
    # temperature/max_tokens go on the client, not .bind(): with_structured_output() drops bound kwargs.
    # A model Settings no longer offers falls back to the default instead of failing every call.
    if model not in settings.available_llm_models():
        model = settings.llm_model
    return _llm(model, temperature, max_tokens)


def chat_model(
    provider: str, base_url: str, api_key: str, model: str, *, temperature: float = 0.0,
    max_tokens: int | None = None, reasoning_effort: str | None = None, key_name: str = "LLM_API_KEY",
    timeout: float = LLM_TIMEOUT_S,
) -> BaseChatModel:
    if provider == "openai":
        return ChatOpenAI(
            model=model,
            api_key=_api_key(api_key, key_name),
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            # Only when set: OpenAI rejects it on non-reasoning models
            **({"reasoning_effort": reasoning_effort} if reasoning_effort else {}),
        )
    return ChatOllama(
        model=model,
        base_url=base_url,
        temperature=temperature,
        num_predict=max_tokens or -1,
        num_ctx=settings.llm_num_ctx,
        client_kwargs={"timeout": timeout},
        # Keeps qwen3 <think> output out of answers and JSON
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
    return chat_model(
        "openai", settings.table_llm_base_url, settings.table_llm_api_key, settings.table_llm_model,
        temperature=temperature, max_tokens=max_tokens, key_name="TABLE_LLM_API_KEY",
    )


def embedding_model(provider: str, base_url: str, api_key: str, model: str) -> Embeddings:
    if provider == "openai":
        return OpenAIEmbeddings(
            model=model,
            api_key=_api_key(api_key, "EMBED_API_KEY"),
            base_url=base_url,
            # Non-OpenAI models are not in tiktoken
            check_embedding_ctx_length=False,
        )
    return OllamaEmbeddings(model=model, base_url=base_url)


@lru_cache
def embeddings() -> Embeddings:
    return embedding_model(settings.embed_provider, settings.embed_base_url, settings.embed_api_key, settings.embed_model)
