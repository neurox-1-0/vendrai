from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings with deliberately unsafe defaults removed."""

    model_config = SettingsConfigDict(
        env_file="../../.env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    APP_ENV: Literal["development", "test", "production"] = "development"
    ALLOW_EXTERNAL_LLM: bool = False
    DEFAULT_MODEL: str = "gemini-2.5-flash"
    API_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "http://localhost:3000"

    DATABASE_URL: str = "postgresql+asyncpg://neurox_app:change-me@localhost:5432/neurox"
    WORKER_DATABASE_URL: str = "postgresql+asyncpg://neurox_worker:change-me@localhost:5432/neurox"
    DATABASE_ECHO: bool = False
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    AUTH_MODE: Literal["development", "keycloak"] = "development"
    KEYCLOAK_ISSUER: str = "http://localhost:8080/realms/neurox"
    KEYCLOAK_JWKS_URL: str = ""
    KEYCLOAK_AUDIENCE: str = "neurox-api"
    DEV_TENANT_ID: str = "00000000-0000-0000-0000-000000000001"
    DEV_USER_ID: str = "00000000-0000-0000-0000-000000000101"

    RABBITMQ_URL: str = "amqp://neurox:change-me@localhost:5672/neurox"
    REDIS_URL: str = "redis://localhost:6379/0"
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    RETRIEVAL_URL: str = "http://retrieval-api:8100"

    STORAGE_BACKEND: Literal["local", "s3"] = "local"
    LOCAL_STORAGE_ROOT: Path = Path("../../.data/object-store")
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_QUARANTINE_BUCKET: str = "neurox-quarantine"
    S3_DOCUMENT_BUCKET: str = "neurox-documents"
    UPLOAD_TOKEN_SECRET: str = "development-only-change-me"
    MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024
    UPLOAD_URL_TTL_SECONDS: int = 900

    CLAMAV_HOST: str = "localhost"
    CLAMAV_PORT: int = 3310
    CLAMAV_REQUIRED: bool = True
    DOCUMENT_PROCESSOR: Literal["docling", "native"] = "native"
    OCR_PRIMARY: str = "tesseract"
    OCR_FALLBACK: str = "easyocr"

    GEMINI_API_KEY: str = ""
    DEFAULT_MODEL: str = "gemini-2.5-flash"
    ALLOW_EXTERNAL_LLM: bool = False
    ALLOW_SYNTHETIC_LLM_DATA_ONLY: bool = True
    DATA_ENCRYPTION_SECRET: str = "development-encryption-secret-change-me"
    BLIND_INDEX_SECRET: str = "development-blind-index-secret-change-me"

    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_FROM: str = "notifications@neurox.local"
    MOCK_ERP_URL: str = "http://mock-erp:8090"

    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4318"

    @model_validator(mode="after")
    def reject_unsafe_production_configuration(self) -> "Settings":
        if self.APP_ENV != "production":
            return self
        problems: list[str] = []
        weak_markers = ("change-me", "change_me", "changeme")
        if self.AUTH_MODE != "keycloak":
            problems.append("AUTH_MODE must be keycloak")
        if any(marker in self.DATABASE_URL.lower() or marker in self.RABBITMQ_URL.lower() for marker in weak_markers):
            problems.append("default database or broker credentials are forbidden")
        if len(self.UPLOAD_TOKEN_SECRET) < 32 or any(marker in self.UPLOAD_TOKEN_SECRET.lower() for marker in weak_markers):
            problems.append("UPLOAD_TOKEN_SECRET must be rotated")
        if any(len(value) < 32 or any(marker in value.lower() for marker in weak_markers) for value in (self.DATA_ENCRYPTION_SECRET, self.BLIND_INDEX_SECRET)):
            problems.append("data protection secrets must be rotated")
        if self.ALLOW_EXTERNAL_LLM and not self.GEMINI_API_KEY:
            problems.append("external LLM is enabled without a provider credential")
        if problems:
            raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
