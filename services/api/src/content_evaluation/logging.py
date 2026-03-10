"""Structured logging helpers."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from time import perf_counter
from uuid import uuid4

from fastapi import Request, Response

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")


def configure_logging() -> None:
    """Configure the application logger once."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s",
    )


def get_logger(name: str) -> logging.LoggerAdapter[logging.Logger]:
    """Return one logger adapter that includes the current request id."""

    return logging.LoggerAdapter(logging.getLogger(name), {"request_id": request_id_context.get()})


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
