"""Settings validation tests."""

import pytest

from content_evaluation.config import Settings
from content_evaluation.domain.exceptions import ConfigurationError
from content_evaluation.domain.models import RuntimeMode


def test_settings_report_live_mode_when_provider_keys_exist() -> None:
    """Detect live mode from configured provider keys."""

    settings = Settings(
        openai_api_key="openai-key",
        tavily_api_key="tavily-key",
    )

    assert settings.runtime_mode is RuntimeMode.LIVE


def test_production_settings_require_live_dependencies() -> None:
    """Fail fast when production mode is missing required settings."""

    with pytest.raises(ConfigurationError, match="CONTENT_EVAL_OPENAI_API_KEY"):
        Settings(app_env="production", cors_origins=["https://app.example.com"])
