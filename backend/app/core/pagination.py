"""Pagination, sorting and search query parameters.

Every collection endpoint is paginated — there is no unbounded list route — so
one tenant with 100k opportunities can never force the API to materialise them
all. ``page_size`` is clamped to the configured maximum rather than rejected,
and sort fields are validated against an explicit allow-list per resource so a
client cannot inject an arbitrary column into ``ORDER BY``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Literal, TypeVar

T = TypeVar("T")

SortOrder = Literal["asc", "desc"]


@dataclass(frozen=True, slots=True)
class PageParams:
    """Validated page window."""

    page: int = 1
    page_size: int = 25

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


@dataclass(frozen=True, slots=True)
class SortParams:
    """Validated ordering instruction."""

    field: str | None = None
    order: SortOrder = "desc"

    @property
    def descending(self) -> bool:
        return self.order == "desc"


@dataclass(frozen=True, slots=True)
class Page(Generic[T]):
    """A repository result page: the rows plus the total matching count."""

    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        if self.page_size <= 0:
            return 0
        return (self.total + self.page_size - 1) // self.page_size


def clamp_page_size(requested: int | None, *, default: int, maximum: int) -> int:
    """Clamp a requested page size into ``[1, maximum]``."""
    if requested is None:
        return default
    return max(1, min(requested, maximum))


def resolve_sort(
    requested: str | None,
    *,
    allowed: frozenset[str],
    default: str,
) -> str:
    """Return a safe ``ORDER BY`` column name.

    Raises:
        ValueError: the requested field is not in the resource's allow-list.
            The API layer turns this into a 422 (see ``value_error_handler``),
            so a client never believes it sorted when it did not.
    """
    if requested is None:
        return default
    if requested not in allowed:
        raise ValueError(f"'{requested}' is not a sortable field; allowed: {sorted(allowed)}")
    return requested
