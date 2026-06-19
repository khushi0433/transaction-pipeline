from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized environment configuration."""

    database_url: str
    redis_url: str
    gemini_api_key: str
    secret_key: str
    max_upload_size_mb: int = 10

    # Pydantic v2 / pydantic-settings v2 configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """Load settings once and reuse them across the process."""
    return Settings()


settings = get_settings()

