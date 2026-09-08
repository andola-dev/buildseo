"""Request-scoped context propagated through contextvars.

Logging, auditing and the database tenant guard all need to know "who is this
request for?" without threading parameters through every function. Contextvars
give that safely under asyncio: each task inherits a copy, so concurrent
requests never observe each other's values.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from uuid import UUID

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_user_id: ContextVar[UUID | None] = ContextVar("user_id", default=None)
_tenant_id: ContextVar[UUID | None] = ContextVar("tenant_id", default=None)
_client_ip: ContextVar[str | None] = ContextVar("client_ip", default=None)
_user_agent: ContextVar[str | None] = ContextVar("user_agent", default=None)


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Immutable snapshot of the ambient request context."""

    request_id: str | None = None
    user_id: UUID | None = None
    tenant_id: UUID | None = None
    client_ip: str | None = None
    user_agent: str | None = None

    def as_log_fields(self) -> dict[str, str]:
        """Non-sensitive fields suitable for log records."""
        fields: dict[str, str] = {}
        if self.request_id:
            fields["request_id"] = self.request_id
        if self.user_id:
            fields["user_id"] = str(self.user_id)
        if self.tenant_id:
            fields["tenant_id"] = str(self.tenant_id)
        return fields


def get_request_context() -> RequestContext:
    """Read the current context snapshot."""
    return RequestContext(
        request_id=_request_id.get(),
        user_id=_user_id.get(),
        tenant_id=_tenant_id.get(),
        client_ip=_client_ip.get(),
        user_agent=_user_agent.get(),
    )


def set_request_id(value: str | None) -> Token[str | None]:
    return _request_id.set(value)


def set_user_id(value: UUID | None) -> Token[UUID | None]:
    return _user_id.set(value)


def set_tenant_id(value: UUID | None) -> Token[UUID | None]:
    return _tenant_id.set(value)


def set_client(ip: str | None, user_agent: str | None) -> None:
    _client_ip.set(ip)
    _user_agent.set(user_agent)


def get_request_id() -> str | None:
    return _request_id.get()


def get_current_user_id() -> UUID | None:
    return _user_id.get()


def get_current_tenant_id() -> UUID | None:
    return _tenant_id.get()


@contextmanager
def request_context(
    *,
    request_id: str | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> Iterator[RequestContext]:
    """Bind a context for the duration of a block, then restore the previous one.

    Used by the request middleware and by the worker runner so background jobs
    log and audit with the same shape as HTTP requests.
    """
    tokens: list[tuple[ContextVar, Token]] = [
        (_request_id, _request_id.set(request_id)),
        (_user_id, _user_id.set(user_id)),
        (_tenant_id, _tenant_id.set(tenant_id)),
        (_client_ip, _client_ip.set(client_ip)),
        (_user_agent, _user_agent.set(user_agent)),
    ]
    try:
        yield get_request_context()
    finally:
        for var, token in reversed(tokens):
            var.reset(token)
