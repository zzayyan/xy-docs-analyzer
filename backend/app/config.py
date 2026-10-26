from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["ollama", "openai"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    llm_provider: Provider = "ollama"
    llm_base_url: str = "http://localhost:11434"
    llm_api_key: str = ""
    llm_model: str = "qwen3:14b"
    # Ollama's default context is small and truncates silently
    llm_num_ctx: int = 16384
    llm_reasoning_effort: str | None = None
    # Comma-separated extra model names on the same endpoint as llm_model
    llm_model_choices: str = ""

    embed_provider: Provider = "ollama"
    embed_base_url: str = "http://localhost:11434"
    embed_api_key: str = ""
    embed_model: str = "bge-m3"
    embed_dim: int = 1024
    tokenizer_model: str = "BAAI/bge-m3"

    # Ingest costs ~10-19 s per PDF page, so these caps bound the wait, not just disk use
    max_upload_mb: int = 100
    max_pages: int = 200

    data_dir: Path = Path(__file__).resolve().parents[1] / "data"

    llm_concurrency: int = 8

    chunk_max_tokens: int = 512
    long_doc_tokens: int = 20000
    context_token_budget: int = 8000

    # Only used while the database has no user at all
    admin_username: str = ""
    admin_password: str = ""
    cookie_secure: bool = False

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password123"

    def available_llm_models(self) -> list[str]:
        extra = [m.strip() for m in self.llm_model_choices.split(",") if m.strip()]
        return [self.llm_model] + [m for m in extra if m != self.llm_model]


settings = Settings()
