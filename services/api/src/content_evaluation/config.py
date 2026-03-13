"""Application settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from content_evaluation.domain.exceptions import ConfigurationError
from content_evaluation.domain.models import AnalysisProviderFamily, OrchestratorBackend, RuntimeMode


class Settings(BaseSettings):
    """Store runtime configuration for the API."""

    model_config = SettingsConfigDict(env_prefix="CONTENT_EVAL_", env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = Field(default="development")
    database_url: str | None = Field(default=None)
    reviewer_name: str = Field(default="Workspace reviewer")
    openai_api_key: str | None = Field(default=None)
    anthropic_api_key: str | None = Field(default=None)
    gemini_api_key: str | None = Field(default=None)
    tavily_api_key: str | None = Field(default=None)
    analysis_provider_family: AnalysisProviderFamily = Field(default=AnalysisProviderFamily.OPENAI)
    openai_model_name: str = Field(default="gpt-4.1-mini")
    anthropic_model_name: str = Field(default="claude-3-5-sonnet-latest")
    gemini_model_name: str = Field(default="gemini-2.0-flash")
    analysis_temperature: float = Field(default=0.0)
    analysis_max_retries: int = Field(default=1)
    agent_max_retries: int = Field(default=2)
    orchestrator_backend: OrchestratorBackend = Field(default=OrchestratorBackend.LANGGRAPH)
    api_base_url: str = Field(default="http://localhost:8000")
    web_base_url: str = Field(default="http://localhost:3000")
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"])
    max_upload_bytes: int = Field(default=524_288)
    worker_poll_interval_seconds: float = Field(default=0.15)
    worker_max_attempts: int = Field(default=2)
    worker_max_concurrent_runs: int = Field(default=3)
    request_timeout_seconds: float = Field(default=30.0)
    provider_timeout_seconds: float = Field(default=90.0)
    sse_stream_timeout_seconds: float = Field(default=900.0)

    @property
    def runtime_mode(self) -> RuntimeMode:
        """Return whether the app is using live or mock providers."""

        if self.analysis_provider_ready and self.tavily_api_key:
            return RuntimeMode.LIVE
        return RuntimeMode.MOCK

    @property
    def analysis_provider_ready(self) -> bool:
        """Return whether the selected analysis provider is configured."""

        if self.analysis_provider_family is AnalysisProviderFamily.OPENAI:
            return self.openai_api_key is not None
        if self.analysis_provider_family is AnalysisProviderFamily.ANTHROPIC:
            return self.anthropic_api_key is not None
        if self.analysis_provider_family is AnalysisProviderFamily.GEMINI:
            return self.gemini_api_key is not None
        return False

    @property
    def persistent_storage_enabled(self) -> bool:
        """Return whether the app uses persistent storage."""

        return self.database_url is not None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _coerce_origins(cls, value: object) -> object:
        """Support comma-separated origins from environment variables."""

        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def validate_runtime(self) -> "Settings":
        """Validate production-safe runtime settings."""

        if self.app_env == "production":
            if self.runtime_mode is RuntimeMode.MOCK:
                raise ConfigurationError(
                    "Production mode requires the configured analysis provider key and CONTENT_EVAL_TAVILY_API_KEY"
                )
            if not self.persistent_storage_enabled:
                raise ConfigurationError("Production mode requires CONTENT_EVAL_DATABASE_URL")
            if not self.cors_origins or "*" in self.cors_origins:
                raise ConfigurationError("Production mode requires explicit non-wildcard CONTENT_EVAL_CORS_ORIGINS")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
