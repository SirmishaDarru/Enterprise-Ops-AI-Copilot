from decimal import Decimal, InvalidOperation
from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    jwt_secret: str
    jwt_issuer: str = "ops-copilot-local"
    access_token_minutes: int = 30
    cors_origin: str = "http://localhost:5173"
    app_env: Literal["development", "test", "production"] = "development"
    embedding_mode: Literal["local", "mock"] = "local"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    investigation_provider: Literal["mock", "openai"] = "mock"
    investigation_model: str = "gpt-4.1-mini"
    openai_api_key: str | None = None
    investigation_timeout_seconds: int = 20
    investigation_input_usd_per_million: str | None = None
    investigation_output_usd_per_million: str | None = None

    @field_validator('investigation_timeout_seconds')
    @classmethod
    def bounded_timeout(cls, value: int) -> int:
        if not 1 <= value <= 60:
            raise ValueError('INVESTIGATION_TIMEOUT_SECONDS must be between 1 and 60')
        return value

    @field_validator('investigation_input_usd_per_million', 'investigation_output_usd_per_million')
    @classmethod
    def nonnegative_rate(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            rate = Decimal(value)
        except InvalidOperation:
            raise ValueError('Investigation rates must be nonnegative decimal numbers') from None
        if not rate.is_finite() or rate < 0:
            raise ValueError('Investigation rates must be nonnegative finite numbers')
        return value

    @field_validator("jwt_secret")
    @classmethod
    def strong_secret(cls, value: str) -> str:
        if len(value.encode()) < 32 or value.startswith("replace_"):
            raise ValueError("JWT_SECRET must be a random value of at least 32 bytes")
        return value

    @field_validator("database_url")
    @classmethod
    def postgres_only(cls, value: str) -> str:
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use postgresql+psycopg")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
