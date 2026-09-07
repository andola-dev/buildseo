"""Structured logging and secret redaction.

Redaction runs inside the logging stack rather than at each call site, so a
careless ``logger.info(payload)`` cannot leak a token. These tests exercise it
through the real handler, not just the helper functions.
"""

from __future__ import annotations

import io
import json
import logging
from uuid import uuid4

import pytest

from app.config.logging import REDACTED, configure_logging, scrub_text, scrub_value
from app.core.context import request_context

pytestmark = pytest.mark.unit


@pytest.fixture
def log_stream() -> io.StringIO:
    configure_logging(level="INFO", json_output=True, service="test", environment="test")
    stream = io.StringIO()
    logging.getLogger().handlers[0].stream = stream
    return stream


def _last_record(stream: io.StringIO) -> dict:
    return json.loads(stream.getvalue().strip().splitlines()[-1])


class TestScrubValue:
    def test_redacts_sensitive_keys_at_any_depth(self) -> None:
        result = scrub_value(
            {
                "password": "hunter2",
                "api_key": "sk-abc",
                "nested": {"Authorization": "Bearer xyz"},
                "list": [{"refresh_token": "t"}],
                "ciphertext": b"\x00\x01",
                "ok": "visible",
            }
        )
        assert result["password"] == REDACTED
        assert result["api_key"] == REDACTED
        assert result["nested"]["Authorization"] == REDACTED
        assert result["list"][0]["refresh_token"] == REDACTED
        assert result["ciphertext"] == REDACTED
        assert result["ok"] == "visible"

    def test_stops_recursing_on_deeply_nested_input(self) -> None:
        deep: dict = {"a": {}}
        cursor = deep["a"]
        for _ in range(20):
            cursor["a"] = {}
            cursor = cursor["a"]
        assert scrub_value(deep)  # must not recurse without bound


class TestScrubText:
    @pytest.mark.parametrize(
        "text",
        [
            "auth: Bearer abcdefghijkl",
            "key=sk-proj-abcdefghijklmnop",
            "key=sk-ant-api03-abcdefghijklmnop",
            "token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghij",
            "google=AIzaSyD-abcdefghijklmnopqrstuv",
        ],
    )
    def test_redacts_secret_shaped_substrings(self, text: str) -> None:
        assert REDACTED in scrub_text(text)

    def test_leaves_ordinary_text_alone(self) -> None:
        assert scrub_text("nothing secret here") == "nothing secret here"


class TestLoggingStack:
    def test_context_is_attached_to_every_record(self, log_stream: io.StringIO) -> None:
        user_id, tenant_id = uuid4(), uuid4()
        with request_context(request_id="req-1", user_id=user_id, tenant_id=tenant_id):
            logging.getLogger("t").info("hello")
        record = _last_record(log_stream)
        assert record["request_id"] == "req-1"
        assert record["user_id"] == str(user_id)
        assert record["tenant_id"] == str(tenant_id)

    def test_secrets_in_args_and_extras_never_reach_the_output(
        self, log_stream: io.StringIO
    ) -> None:
        logging.getLogger("t").info(
            "login for %s",
            {"email": "a@b.c", "password": "hunter2"},
            extra={"api_key": "sk-livekey123456789", "endpoint": "/auth/login"},
        )
        record = _last_record(log_stream)
        assert record["api_key"] == REDACTED
        assert record["endpoint"] == "/auth/login"
        assert "hunter2" not in json.dumps(record)

    def test_records_carry_the_expected_envelope(self, log_stream: io.StringIO) -> None:
        logging.getLogger("t").warning("careful")
        record = _last_record(log_stream)
        assert record["level"] == "WARNING"
        assert record["service"] == "test"
        assert record["environment"] == "test"
        assert "timestamp" in record

    def test_exceptions_are_formatted_into_the_record(self, log_stream: io.StringIO) -> None:
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            logging.getLogger("t").exception("failed")
        record = _last_record(log_stream)
        assert "Traceback" in record["exception"]

    def test_context_does_not_leak_between_requests(self, log_stream: io.StringIO) -> None:
        with request_context(request_id="req-1", tenant_id=uuid4()):
            logging.getLogger("t").info("scoped")
        logging.getLogger("t").info("unscoped")
        record = _last_record(log_stream)
        assert "request_id" not in record
        assert "tenant_id" not in record
