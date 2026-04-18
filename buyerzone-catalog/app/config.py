from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Telegram ──────────────────────────────────────────────────────────────
    telegram_api_id: int
    telegram_api_hash: str
    telegram_session_name: str = "buyerzone"

    # ── PostgreSQL ─────────────────────────────────────────────────────────────
    database_url: str  # postgresql+asyncpg://...
    db_password: str | None = None  # kept for reference, not used directly

    # ── Qdrant ─────────────────────────────────────────────────────────────────
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "product_embeddings"
    qdrant_url: str | None = None                   # cloud URL overrides host+port when set
    qdrant_cluster_endpoint: str | None = None      # alias some dashboards export
    qdrant_api_key: str | None = None

    # ── Redis ──────────────────────────────────────────────────────────────────
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str | None = None

    # ── S3-compatible Storage (Cloudflare R2) ──────────────────────────────────
    s3_access_key_id: str
    s3_secret_access_key: str
    s3_bucket_name: str
    s3_public_url: str  # CDN base URL
    s3_endpoint_url: str  # e.g. https://<account_id>.r2.cloudflarestorage.com
    s3_region: str = "auto"

    # ── Security ───────────────────────────────────────────────────────────────
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 10080  # 1 week
    internal_api_key: str

    # ── App behaviour ─────────────────────────────────────────────────────────
    environment: str = "development"
    log_level: str = "INFO"
    dedup_similarity_threshold: float = 0.96
    # Minimum cosine similarity for a Qdrant result to be returned from
    # /search/image and /search/combined. 0.75 = "clearly same product,
    # possibly different photo"; raise toward 0.90 for near-identical only.
    search_similarity_threshold: float = 0.75
    staleness_days: int = 30
    ingestion_internal_port: int = 8001
    ingestion_internal_url: str = "http://localhost:8001"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def redis_url_with_auth(self) -> str:
        """Redis URL with password embedded, used by aioredis."""
        if self.redis_password:
            return f"rediss://default:{self.redis_password}@{self.redis_host}:{self.redis_port}"
        return f"rediss://{self.redis_host}:{self.redis_port}"

    @property
    def arq_redis_settings(self):
        """ARQ RedisSettings built from individual host/port/password fields."""
        from arq.connections import RedisSettings
        return RedisSettings(
            host=self.redis_host,
            port=self.redis_port,
            password=self.redis_password or None,
            ssl=True,
            ssl_cert_reqs=None,
            conn_timeout=15,        # SSL handshake to cloud Redis needs headroom
            conn_retries=10,        # tolerate transient network blips
            conn_retry_delay=2,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
