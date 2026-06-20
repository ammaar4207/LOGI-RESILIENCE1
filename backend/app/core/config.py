import logging
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings



class Settings(BaseSettings):
    APP_NAME: str = "Logi-Resilience"
    APP_VERSION: str = "4.0.0"
    ENVIRONMENT: str = "production"  # Fail-secure default
    DEBUG: bool = False

    NEO4J_URI: str = "bolt://neo4j:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "mca_secure_password_2026"

    REDIS_URL: str = "redis://redis:6379"
    REDIS_STREAM_CHANNEL: str = "live_logistics_stream"
    REDIS_CACHE_TTL_SECONDS: int = 900

    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    KAFKA_TELEMETRY_TOPIC: str = "logistics.telemetry"
    KAFKA_ENABLED: bool = False

    # PostgreSQL Database Settings
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "mca_postgres_password_2026"
    POSTGRES_DB: str = "logiresilience"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: str = "5432"

    # MinIO / Object Storage Settings
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "minio_admin"
    MINIO_SECRET_KEY: str = "minio_admin_secret_2026"
    MINIO_BUCKET: str = "model-registry"
    MINIO_SECURE: bool = False

    # MLflow Settings
    MLFLOW_TRACKING_URI: str = "http://mlflow:5000"

    # Celery Settings
    CELERY_BROKER_URL: str = "redis://redis:6379/1"

    WEATHER_API_KEY: str = ""
    NEWS_API_KEY: str = ""
    OPENWEATHER_BASE_URL: str = "https://api.openweathermap.org/data/2.5/weather"
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "mistral:7b-instruct"   # Best free quality model via Ollama

    MODEL_CHECKPOINT_PATH: str = "model_physics.pt"
    WORKER_POLL_INTERVAL_SECONDS: float = 5.0
    SLACK_WEBHOOK_URL: str = ""

    CORS_ORIGINS: List[str] = ["*"]

    SECRET_KEY: str = "change-me-in-production-use-secrets-manager"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    RATE_LIMIT_SIMULATE: str = "30/minute"

    @property
    def postgres_url(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    try:
        from app.core.vault import fetch_vault_secrets
        vault_secrets = fetch_vault_secrets()
        
        # Determine valid settings fields for both Pydantic v1 and v2 compatibility
        if hasattr(Settings, "model_fields"):
            valid_keys = Settings.model_fields.keys()
        else:
            valid_keys = Settings.__fields__.keys()
            
        filtered_secrets = {k: v for k, v in vault_secrets.items() if k in valid_keys and v is not None}
        return Settings(**filtered_secrets)
    except Exception as exc:
        logging.getLogger("logi-resilience").warning("Error resolving settings with Vault: %s. Using default env.", exc)
        return Settings()

