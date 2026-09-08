"""Structured application logging.

Two formatters share one redaction pipeline: a JSON formatter for production
log shipping and a readable console formatter for development. Every record
passes through :class:`SecretRedactionFilter` *before* formatting, so a
careless ``logger.info("payload=%s", body)`` cannot leak a token — redaction is
a property of the logging stack, not of each call site.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.core.context import get_request_context

#: Keys whose values are replaced wholesale, matched case-insensitively as a
#: substring so ``x_api_key``, ``provider_secret`` and ``Authorization`` all hit.
SENSITIVE_KEY_PARTS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "authorization",
        "auth_header",
        "api_key",
        "apikey",
        "access_key",
        "private_key",
        "encryption_key",
        "master_key",
        "credential",
        "ciphertext",
        "encrypted_dek",
        "dek",
        "cookie",
        "set-cookie",
        "session_token",
        "refresh_token",
        "client_secret",
        "signature",
    }
)

REDACTED = "***REDACTED***"

#: Value-shaped patterns, for secrets that arrive inside a free-text message
#: rather than under a recognisable key.
_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._\-+/=]{8,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b"),  # JWT
    re.compile(r"\b(sk|rk|pk|xai|gsk)-[A-Za-z0-9_\-]{12,}\b"),  # provider API keys
    re.compile(r"\bAIza[A-Za-z0-9_\-]{20,}\b"),  # Google API keys
    re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{12,}\b"),  # Anthropic keys
)

_RESERVED_RECORD_KEYS = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def scrub_value(value: Any, *, depth: int = 0) -> Any:
    """Recursively redact sensitive keys and secret-shaped strings."""
    if depth > 6:
        return "<truncated>"
    if isinstance(value, Mapping):
        return {
            key: (REDACTED if _is_sensitive_key(str(key)) else scrub_value(item, depth=depth + 1))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [scrub_value(item, depth=depth + 1) for item in value]
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<{len(bytes(value))} bytes>"
    return value


def scrub_text(text: str) -> str:
    """Redact secret-shaped substrings from free text."""
    scrubbed = text
    for pattern in _VALUE_PATTERNS:
        scrubbed = pattern.sub(REDACTED, scrubbed)
    return scrubbed


class SecretRedactionFilter(logging.Filter):
    """Scrubs the message, positional args and structured extras of a record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = scrub_text(record.msg)
        if record.args:
            if isinstance(record.args, Mapping):
                record.args = scrub_value(dict(record.args))  # type: ignore[assignment]
            else:
                record.args = tuple(scrub_value(arg) for arg in record.args)
        for key, value in list(record.__dict__.items()):
            if key in _RESERVED_RECORD_KEYS:
                continue
            record.__dict__[key] = REDACTED if _is_sensitive_key(key) else scrub_value(value)
        return True


class RequestContextFilter(logging.Filter):
    """Attaches request_id / user_id / tenant_id from the ambient context."""

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in get_request_context().as_log_fields().items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line, suitable for any log aggregator."""

    def __init__(self, *, service: str, environment: str) -> None:
        super().__init__()
        self._service = service
        self._environment = environment

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self._service,
            "environment": self._environment,
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED_RECORD_KEYS or key in payload:
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, separators=(",", ":"))


class ConsoleFormatter(logging.Formatter):
    """Compact human-readable output for local development."""

    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)-8s %(name)s %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = {
            key: value for key, value in record.__dict__.items() if key not in _RESERVED_RECORD_KEYS
        }
        return f"{base} {extras}" if extras else base


def configure_logging(*, level: str, json_output: bool, service: str, environment: str) -> None:
    """Install the logging stack. Idempotent, so tests may call it repeatedly."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter(service=service, environment=environment)
        if json_output
        else ConsoleFormatter()
    )
    handler.addFilter(RequestContextFilter())
    handler.addFilter(SecretRedactionFilter())

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Uvicorn duplicates access logs through its own handlers; route them here.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    # SQLAlchemy echoes full SQL at INFO; keep it at WARNING unless debugging.
    logging.getLogger("sqlalchemy.engine").setLevel("WARNING")


def get_logger(name: str) -> logging.Logger:
    """Return a module logger."""
    return logging.getLogger(name)
