"""Logging tests."""

from __future__ import annotations

import logging

from content_evaluation.logging import configure_logging, get_logger, request_id_context


def test_configure_logging_injects_default_request_id() -> None:
    """Attach a request id to third-party log records before formatting."""

    configure_logging()
    token = request_id_context.set("req-test-123")
    try:
        record = logging.getLogRecordFactory()(
            "httpx",
            logging.INFO,
            __file__,
            12,
            "HTTP Request: %s",
            ("ok",),
            None,
        )
    finally:
        request_id_context.reset(token)

    assert record.request_id == "req-test-123"


def test_get_logger_does_not_overwrite_request_id() -> None:
    """Return a plain logger so request id injection does not collide with extra fields."""

    configure_logging()
    logger = get_logger("content_evaluation.test")

    assert not isinstance(logger, logging.LoggerAdapter)
