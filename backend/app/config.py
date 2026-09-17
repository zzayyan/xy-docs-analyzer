from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["ollama", "openai"]


class Settings(BaseSettings):
    """LLM and embeddings are configured per role: they often live on different servers."""

    model_config = SettingsConfigDict(env_file=".env")

    # "openai" covers any OpenAI-compatible server: vLLM, OpenRouter, OpenAI itself
    llm_provider: Provider = "ollama"
    llm_base_url: str = "http://localhost:11434"
    llm_api_key: str = ""
    llm_model: str = "qwen3:14b"
    # Ollama's default context is small and truncates silently; ignored by OpenAI-compatible servers
    llm_num_ctx: int = 16384
    # Extra model names selectable per document at upload time, alongside llm_model (the default).
    # Comma-separated; every one must be reachable through the single llm_provider/llm_base_url/
    # llm_api_key above -- this offers model *names*, not a second provider.
    llm_model_choices: str = ""

    embed_provider: Provider = "ollama"
    embed_base_url: str = "http://localhost:11434"
    embed_api_key: str = ""
    embed_model: str = "bge-m3"
    embed_dim: int = 1024
    tokenizer_model: str = "BAAI/bge-m3"

    # Ingest costs roughly 10-19 s per PDF page end to end, so these caps bound the wait, not just disk use
    max_upload_mb: int = 100
    max_pages: int = 200

    # Originals are kept here as originals/<document id><extension> until their Document is deleted.
    # Defaults to backend/data regardless of the directory the server is started from.
    data_dir: Path = Path(__file__).resolve().parents[1] / "data"

    # Section summaries and knowledge-graph extraction are one LLM call each; this is how many run at once
    llm_concurrency: int = 8

    chunk_max_tokens: int = 512
    long_doc_tokens: int = 20000
    context_token_budget: int = 8000

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password123"

    def available_llm_models(self) -> list[str]:
        extra = [m.strip() for m in self.llm_model_choices.split(",") if m.strip()]
        return [self.llm_model] + [m for m in extra if m != self.llm_model]


settings = Settings()
