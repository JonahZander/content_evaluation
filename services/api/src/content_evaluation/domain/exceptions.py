"""Typed domain exceptions."""


class ContentEvaluationError(Exception):
    """Base exception for the content evaluation domain."""


class NotFoundError(ContentEvaluationError):
    """Raise when a requested entity does not exist."""


class ValidationError(ContentEvaluationError):
    """Raise when the request shape is invalid."""


class ProviderError(ContentEvaluationError):
    """Raise when an upstream provider fails."""

    def __init__(
        self,
        message: str,
        *,
        kind: str = "provider_error",
        retriable: bool = False,
        fallback_eligible: bool = False,
        provider_name: str | None = None,
    ) -> None:
        """Store retry and provider metadata alongside the message."""

        super().__init__(message)
        self.kind = kind
        self.retriable = retriable
        self.fallback_eligible = fallback_eligible
        self.provider_name = provider_name


class ConfigurationError(ContentEvaluationError):
    """Raise when the runtime configuration is invalid."""


class RunCancelledError(ContentEvaluationError):
    """Raise when a run is cancelled mid-execution."""
