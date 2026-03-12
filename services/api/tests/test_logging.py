"""Logging tests."""

from __future__ import annotations

import logging

from content_evaluation.logging import configure_logging, request_id_context


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

    assert getattr(record, "request_id") == "req-test-123"
