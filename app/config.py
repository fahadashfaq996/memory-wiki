from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Database ---
    database_url: str = "postgresql+psycopg2://memory:memory@postgres:5432/memory"

    # --- Redis / job queue ---
    redis_url: str = "redis://redis:6379/0"
    job_queue_key: str = "memory:jobs"

    # --- Object store (S3 compatible; MinIO by default) ---
    s3_endpoint_url: str | None = "http://minio:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "memories"
    s3_region: str = "us-east-1"
    # Root prefix inside the bucket that holds the memory file tree.
    memory_prefix: str = "memories"

    # --- LLM ---
    # "openrouter" for real generation, "fake" for a deterministic offline stub.
    llm_provider: str = "openrouter"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    llm_request_timeout: float = 60.0

    # --- Worker reliability ---
    max_attempts: int = 5
    # Base for exponential backoff: delay = base * 2**(attempt-1) (+ jitter).
    retry_backoff_seconds: float = 2.0
    # Upper bound on any single retry wait, including a provider's Retry-After.
    max_retry_delay_seconds: float = 120.0
    # Random jitter added to each backoff to avoid thundering-herd retries.
    retry_jitter_seconds: float = 1.0
    # A job stuck in `processing` longer than this is considered abandoned and
    # is re-queued on worker startup.
    processing_timeout_seconds: int = 300
    queue_poll_timeout: int = 5

    @property
    def llm_is_fake(self) -> bool:
        return self.llm_provider.strip().lower() == "fake"


@lru_cache
def get_settings() -> Settings:
    return Settings()
