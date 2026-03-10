"""Application settings."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Store runtime configuration for the API."""

    model_config = SettingsConfigDict(env_prefix="CONTENT_EVAL_", env_file=".env", extra="ignore")

    app_env: str = Field(default="development")
    database_url: str | None = Field(default=None)
    reviewer_name: str = Field(default="Workspace reviewer")
    openai_api_key: str | None = Field(default=None)
    tavily_api_key: str | None = Field(default=None)
    api_base_url: str = Field(default="http://localhost:8000")
    web_base_url: str = Field(default="http://localhost:3000")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
