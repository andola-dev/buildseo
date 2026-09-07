"""The single response envelope used by every endpoint.

Success payloads are always ``{"data": ..., "meta": {...}}`` and failures are
always ``{"error": {"code", "message", "details"}}``. Clients can therefore
branch on shape alone, and adding pagination or rate-limit metadata later never
changes where the payload lives.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ResponseMeta(BaseModel):
    """Free-form, non-paginated metadata."""

    model_config = ConfigDict(extra="allow")


class PaginationMeta(BaseModel):
    """Page counters returned with every collection response."""

    page: int = Field(ge=1, description="Current 1-based page number")
    page_size: int = Field(ge=1, description="Number of items requested per page")
    total: int = Field(ge=0, description="Total number of items matching the filters")
    total_pages: int = Field(ge=0, description="Total number of pages available")
    has_next: bool = Field(description="Whether a following page exists")
    has_previous: bool = Field(description="Whether a preceding page exists")

    @classmethod
    def build(cls, *, page: int, page_size: int, total: int) -> PaginationMeta:
        total_pages = (total + page_size - 1) // page_size if page_size else 0
        return cls(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1 and total_pages > 0,
        )


class ApiResponse(BaseModel, Generic[T]):
    """Envelope for a single resource."""

    data: T
    meta: dict[str, Any] = Field(default_factory=dict)


class PaginatedResponse(BaseModel, Generic[T]):
    """Envelope for a collection of resources."""

    data: list[T]
    meta: PaginationMeta


class ErrorDetail(BaseModel):
    """Machine-readable error body. Never carries stack traces or SQL."""

    code: str = Field(description="Stable, machine-readable error identifier")
    message: str = Field(description="Human-readable, caller-safe description")
    details: dict[str, Any] = Field(
        default_factory=dict, description="Structured context such as field errors"
    )


class ErrorResponse(BaseModel):
    """Envelope for every failure response."""

    error: ErrorDetail


def ok(data: T, **meta: Any) -> ApiResponse[T]:
    """Wrap a single resource in the success envelope."""
    return ApiResponse[T](data=data, meta=meta)


def paginated(items: list[T], *, page: int, page_size: int, total: int) -> PaginatedResponse[T]:
    """Wrap a page of resources in the collection envelope."""
    return PaginatedResponse[T](
        data=items, meta=PaginationMeta.build(page=page, page_size=page_size, total=total)
    )


#: Reusable OpenAPI response declarations so every route documents its failures.
ERROR_RESPONSE_SCHEMA: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse, "description": "Malformed request"},
    401: {"model": ErrorResponse, "description": "Authentication required or failed"},
    403: {"model": ErrorResponse, "description": "Permission or tenant access denied"},
    404: {"model": ErrorResponse, "description": "Resource not found"},
    409: {"model": ErrorResponse, "description": "Conflict with current resource state"},
    422: {"model": ErrorResponse, "description": "Validation or business-rule failure"},
    429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    500: {"model": ErrorResponse, "description": "Unexpected server error"},
}

AUTH_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: ERROR_RESPONSE_SCHEMA[code] for code in (401, 403, 429, 500)
}

CRUD_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: ERROR_RESPONSE_SCHEMA[code] for code in (401, 403, 404, 422, 429, 500)
}
