from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import PostgresDsn, computed_field
from typing import Optional
from sqlalchemy import URL

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='../../.env',
        env_file_encoding='utf-8',
        case_sensitive=True,
        extra='ignore'
    )
    
    # PostgreSQL
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "vendortopay"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    
    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # LLM
    GEMINI_API_KEY: str = ""
    DEFAULT_MODEL: str = "gemini-2.5-flash"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

settings = Settings()
