"""Typed domain exceptions."""


class ContentEvaluationError(Exception):
    """Base exception for the content evaluation domain."""


class NotFoundError(ContentEvaluationError):
    """Raise when a requested entity does not exist."""


class ValidationError(ContentEvaluationError):
    """Raise when the request shape is invalid."""


class ProviderError(ContentEvaluationError):
    """Raise when an upstream provider fails."""
