"""Structured logging helpers."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from time import perf_counter
from uuid import uuid4

from fastapi import Request, Response

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")
_LOG_RECORD_FACTORY = logging.getLogRecordFactory()


def _record_factory(*args: object, **kwargs: object) -> logging.LogRecord:
    """Ensure every log record has the request id field expected by the formatter."""

    record = _LOG_RECORD_FACTORY(*args, **kwargs)
    if not hasattr(record, "request_id"):
        record.request_id = request_id_context.get()
    return record


def configure_logging() -> None:
    """Configure the application logger once."""

    logging.setLogRecordFactory(_record_factory)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s",
    )
    for logger_name in ("httpx", "httpcore", "openai", "openai._base_client"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return one logger that relies on the record factory for request id injection."""

    return logging.getLogger(name)


async def request_logging_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Log one request lifecycle with a stable request id."""

    request_id = request.headers.get("x-request-id", str(uuid4()))
    token = request_id_context.set(request_id)
    started_at = perf_counter()
    logger = get_logger("content_evaluation.request")
    logger.info("request started method=%s path=%s", request.method, request.url.path)
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = (perf_counter() - started_at) * 1000
        logger.exception("request failed path=%s elapsed_ms=%.2f", request.url.path, elapsed_ms)
        request_id_context.reset(token)
        raise
    elapsed_ms = (perf_counter() - started_at) * 1000
    response.headers["x-request-id"] = request_id
    logger.info(
        "request completed method=%s path=%s status=%s elapsed_ms=%.2f",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    request_id_context.reset(token)
    return response
