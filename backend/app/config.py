from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    database_url: str = "postgresql://documind:documind@localhost:5432/documind"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    cache_enabled: bool = True
    embedding_cache_ttl_seconds: int = 86_400
    answer_cache_ttl_seconds: int = 600

    llm_provider: str = "gemini"
    generation_provider: str = "local"
    embedding_provider: str = "local"
    embedding_dimension: int = 384
    reranker_provider: str = "local"
    reranker_candidate_multiplier: int = 4
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    evaluation_provider: str = "local"
    ragas_llm_model: str = "gemini-2.0-flash"
    ragas_embedding_model: str = "gemini-embedding-001"
    gemini_generation_model: str = "gemini-2.5-flash-lite"
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_api_key: str | None = None
    gemini_temperature: float = 0.2
    openai_api_key: str | None = None
    openai_generation_model: str = "gpt-4.1-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    cloudflare_r2_endpoint_url: str | None = None
    cloudflare_r2_access_key_id: str | None = None
    cloudflare_r2_secret_access_key: str | None = None
    cloudflare_r2_bucket: str | None = None
    document_storage_provider: str = "local"
    local_document_storage_dir: str = "storage/source-documents"
    url_fetch_timeout_seconds: float = 10.0
    url_fetch_max_bytes: int = 2_000_000

    app_name: str = Field(default="DocuMind API", frozen=True)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
