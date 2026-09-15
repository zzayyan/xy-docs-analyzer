from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # Provider selection: "ollama" or "openrouter"
    provider: str = "ollama"

    # Ollama settings
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen3:14b"
    llm_num_ctx: int = 16384
    embed_model: str = "bge-m3"
    embed_dim: int = 1024
    tokenizer_model: str = "BAAI/bge-m3"

    # OpenRouter settings
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_llm_model: str = "openrouter/free"
    openrouter_embed_model: str = "nvidia/nemotron-3-embed-1b:free"
    openrouter_embed_dim: int = 2048

    chunk_max_tokens: int = 512
    long_doc_tokens: int = 20000
    context_token_budget: int = 8000

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password123"

    @property
    def embed_dim_active(self) -> int:
        """Return the embedding dimension for the active provider."""
        return self.openrouter_embed_dim if self.provider == "openrouter" else self.embed_dim


settings = Settings()
