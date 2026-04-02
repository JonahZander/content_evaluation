"""Settings validation tests."""

import pytest

from content_evaluation.config import Settings, get_settings, reset_settings
from content_evaluation.domain.exceptions import ConfigurationError
from content_evaluation.domain.models import AnalysisProviderFamily, OrchestratorBackend, RuntimeMode


def test_settings_report_live_mode_when_provider_keys_exist() -> None:
    """Detect live mode from configured provider keys."""

    settings = Settings(
        openai_api_key="openai-key",
        tavily_api_key="tavily-key",
    )

    assert settings.runtime_mode is RuntimeMode.LIVE
    assert settings.analysis_provider_family is AnalysisProviderFamily.OPENAI
    assert settings.orchestrator_backend is OrchestratorBackend.LANGGRAPH


def test_production_settings_require_live_dependencies() -> None:
    """Fail fast when production mode is missing required settings."""

    with pytest.raises(ConfigurationError, match="configured analysis provider key"):
        Settings(
            app_env="production",
            cors_origins=["https://app.example.com"],
            openai_api_key=None,
            anthropic_api_key=None,
            gemini_api_key=None,
            tavily_api_key=None,
        )


def test_reset_settings_reloads_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Allow tests to replace environment-driven settings between calls."""

    reset_settings()
    monkeypatch.setenv("CONTENT_EVAL_REVIEWER_NAME", "First reviewer")
    assert get_settings().reviewer_name == "First reviewer"

    monkeypatch.setenv("CONTENT_EVAL_REVIEWER_NAME", "Second reviewer")
    assert get_settings().reviewer_name == "First reviewer"

    reset_settings()
    assert get_settings().reviewer_name == "Second reviewer"
    reset_settings()


def test_settings_reject_legacy_orchestrator_backend() -> None:
    """Fail fast when the removed legacy backend is requested."""

    with pytest.raises(ConfigurationError, match="no longer supported"):
        Settings(orchestrator_backend=OrchestratorBackend.LEGACY)
