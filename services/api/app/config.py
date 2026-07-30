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
    # Direct-grant credentials for the role-separated realm users the
    # acceptance bootstrap provisions. Used by the bootstrap to authenticate as
    # an administrator, and by the browser acceptance suite to log in as each
    # role. Never used to authorise a request - the API still checks the token.
    KEYCLOAK_E2E_CLIENT_SECRET: str = ""
    KEYCLOAK_E2E_USER_PASSWORD: str = ""
    DEV_TENANT_ID: str = "00000000-0000-0000-0000-000000000001"
    DEV_USER_ID: str = "00000000-0000-0000-0000-000000000101"

    RABBITMQ_URL: str = "amqp://neurox:change-me@localhost:5672/neurox"
    REDIS_URL: str = "redis://localhost:6379/0"
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    RETRIEVAL_URL: str = "http://retrieval-api:8100"
    OPA_URL: str = "http://opa:8181"
    # Third-party risk screening (adverse media, country risk). Distinct from
    # sanctions screening, which runs against locally imported official lists.
    RISK_SERVICE_URL: str = "http://mock-risk:8095"
    RISK_SERVICE_TIMEOUT_SECONDS: float = 10.0

    STORAGE_BACKEND: Literal["local", "s3"] = "local"
    LOCAL_STORAGE_ROOT: Path = Path("../../.data/object-store")
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_PUBLIC_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_REGION: str = "us-east-1"
    S3_QUARANTINE_BUCKET: str = "neurox-quarantine"
    S3_DOCUMENT_BUCKET: str = "neurox-documents"
    UPLOAD_TOKEN_SECRET: str = "development-only-change-me"
    MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024
    MAX_PDF_PAGES: int = 100
    UPLOAD_URL_TTL_SECONDS: int = 900

    CLAMAV_HOST: str = "localhost"
    CLAMAV_PORT: int = 3310
    CLAMAV_REQUIRED: bool = True
    DOCUMENT_PROCESSOR: Literal["docling", "native"] = "native"
    OCR_PRIMARY: str = "tesseract"
    OCR_FALLBACK: str = "easyocr"
    OCR_MIN_NATIVE_CHARACTERS: int = 40
    OCR_MIN_CONFIDENCE: float = 0.60
    EASYOCR_MODEL_DIR: str = "/opt/easyocr"

    GEMINI_API_KEY: str = ""
    DEFAULT_MODEL: str = "gemini-3.6-flash"
    ALLOW_EXTERNAL_LLM: bool = False
    ALLOW_SYNTHETIC_LLM_DATA_ONLY: bool = True
    LLM_DATA_CLASSIFICATION: Literal["SYNTHETIC", "TOKENIZED"] = "SYNTHETIC"
    LLM_MAX_ATTEMPTS: int = 3
    LLM_TIMEOUT_SECONDS: int = 45
    LLM_CONCURRENCY: int = 4
    LLM_CIRCUIT_FAILURE_THRESHOLD: int = 5
    LLM_CIRCUIT_RESET_SECONDS: int = 120
    DATA_ENCRYPTION_SECRET: str = "development-encryption-secret-change-me"
    BLIND_INDEX_SECRET: str = "development-blind-index-secret-change-me"

    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_FROM: str = "notifications@neurox.local"
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_STARTTLS: bool = False
    SMTP_USE_SSL: bool = False
    MOCK_ERP_URL: str = "http://mock-erp:8090"

    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4318"
    OTEL_SERVICE_NAME: str = "neurox-api"
    OTEL_ENABLED: bool = False
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 120
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    LIVE_PROGRESS_ENABLED: bool = True
    LIVE_PROGRESS_TTL_SECONDS: int = 900
    LIVE_PROGRESS_REDIS_TIMEOUT_SECONDS: float = 0.25
    SANCTIONS_MAX_AGE_HOURS: int = 36
    SANCTIONS_DOWNLOAD_MAX_BYTES: int = 64 * 1024 * 1024
    SANCTIONS_OFAC_URL: str = (
        "https://sanctionslistservice.ofac.treas.gov/api/"
        "PublicationPreview/exports/SDN.XML"
    )
    SANCTIONS_UN_URL: str = (
        "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
    )
    SANCTIONS_EU_URL: str = ""
    ALERT_EVALUATION_INTERVAL_SECONDS: int = 900
    ALERT_TENANT_IDS: str = ""

    # Reference data, policies, and case documents the bootstrap loads. Mounted
    # read-only rather than baked into the image: it is several hundred
    # megabytes of PDFs that only the bootstrap and the evaluation harness read.
    CORPUS_ROOT: Path = Path("/srv/corpus")
    # Base URL the bootstrap uses to drive the product's own API. Loading data
    # through the public interface, rather than writing rows, means the
    # bootstrap exercises authorization, idempotency, audit, and indexing on
    # every run - it is the first integration test as well as a data load.
    BOOTSTRAP_API_URL: str = "http://localhost:8000"
    # Bounded wait for the retrieval worker to index a freshly published
    # policy. Returning before indexing completes would report success while
    # retrieval still answers nothing.
    BOOTSTRAP_INDEXING_TIMEOUT_SECONDS: int = 180

    @model_validator(mode="after")
    def reject_unsafe_production_configuration(self) -> "Settings":
        if self.APP_ENV != "production":
            return self
        problems: list[str] = []
        weak_markers = ("change-me", "change_me", "changeme")
        if self.AUTH_MODE != "keycloak":
            problems.append("AUTH_MODE must be keycloak")
        if self.STORAGE_BACKEND != "s3":
            problems.append("STORAGE_BACKEND must be s3")
        if any(marker in self.DATABASE_URL.lower() or marker in self.RABBITMQ_URL.lower() for marker in weak_markers):
            problems.append("default database or broker credentials are forbidden")
        if len(self.UPLOAD_TOKEN_SECRET) < 32 or any(marker in self.UPLOAD_TOKEN_SECRET.lower() for marker in weak_markers):
            problems.append("UPLOAD_TOKEN_SECRET must be rotated")
        if any(len(value) < 32 or any(marker in value.lower() for marker in weak_markers) for value in (self.DATA_ENCRYPTION_SECRET, self.BLIND_INDEX_SECRET)):
            problems.append("data protection secrets must be rotated")
        if self.ALLOW_EXTERNAL_LLM and not self.GEMINI_API_KEY:
            problems.append("external LLM is enabled without a provider credential")
        if self.DEFAULT_MODEL != "gemini-3.6-flash":
            problems.append("DEFAULT_MODEL must be pinned to gemini-3.6-flash")
        if (
            self.ALLOW_EXTERNAL_LLM
            and self.LLM_DATA_CLASSIFICATION != "TOKENIZED"
        ):
            problems.append(
                "production external LLM payloads must be TOKENIZED"
            )
        if self.SMTP_STARTTLS and self.SMTP_USE_SSL:
            problems.append("SMTP_STARTTLS and SMTP_USE_SSL are mutually exclusive")
        if problems:
            raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
