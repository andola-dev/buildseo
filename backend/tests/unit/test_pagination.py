"""Pagination and sort-field validation."""

from __future__ import annotations

import pytest

from app.core.exceptions import AppError, InvalidSortFieldError
from app.core.pagination import Page, PageParams, SortParams, clamp_page_size, resolve_sort

pytestmark = pytest.mark.unit


class TestPageParams:
    def test_offset_and_limit_follow_the_page_window(self) -> None:
        params = PageParams(page=3, page_size=25)
        assert params.offset == 50
        assert params.limit == 25

    def test_first_page_starts_at_zero(self) -> None:
        assert PageParams().offset == 0


class TestClampPageSize:
    @pytest.mark.parametrize(
        ("requested", "expected"),
        [(None, 25), (50, 50), (500, 100), (0, 1), (-7, 1), (100, 100)],
    )
    def test_clamps_into_the_allowed_range(self, requested: int | None, expected: int) -> None:
        # Clamping rather than rejecting: a client asking for too much gets the
        # maximum page, and the database's work stays bounded either way.
        assert clamp_page_size(requested, default=25, maximum=100) == expected


class TestResolveSort:
    ALLOWED = frozenset({"created_at", "quality_score"})

    def test_falls_back_to_the_default(self) -> None:
        assert resolve_sort(None, allowed=self.ALLOWED, default="created_at") == "created_at"

    def test_accepts_an_allowed_field(self) -> None:
        assert (
            resolve_sort("quality_score", allowed=self.ALLOWED, default="created_at")
            == "quality_score"
        )

    @pytest.mark.parametrize(
        "field", ["tenant_id", "password_hash", "1; DROP TABLE publishers", "ciphertext"]
    )
    def test_rejects_a_field_outside_the_allow_list(self, field: str) -> None:
        # Rejecting rather than ignoring: a client must never believe it sorted
        # when it did not, and ORDER BY must never take arbitrary input.
        with pytest.raises(ValueError):
            resolve_sort(field, allowed=self.ALLOWED, default="created_at")

    def test_the_rejection_names_the_fields_the_caller_may_use(self) -> None:
        with pytest.raises(InvalidSortFieldError) as raised:
            resolve_sort("password_hash", allowed=self.ALLOWED, default="created_at")
        assert raised.value.details["allowed"] == sorted(self.ALLOWED)
        assert raised.value.details["field"] == "password_hash"


class TestInvalidSortFieldError:
    """The dual inheritance is load-bearing and otherwise invisible.

    ``resolve_sort`` is called from the repository, not from a request
    dependency, so the natural exception for it to raise is a ``ValueError`` —
    and non-API callers catch one. Being an ``AppError`` *as well* is what
    makes the API return the intended 422: Starlette picks a handler by walking
    ``type(exc).__mro__``, so ``AppError`` must come before ``ValueError``
    there. Reordering the bases, or dropping either one, would silently turn
    every rejected sort field into a 500 (or, worse, invite a blanket
    ``ValueError`` handler that reclassifies real defects as client errors).
    """

    def test_it_is_catchable_as_a_plain_value_error(self) -> None:
        error = InvalidSortFieldError.for_field("x", allowed=frozenset({"created_at"}))
        assert isinstance(error, ValueError)

    def test_it_carries_the_422_from_app_error(self) -> None:
        error = InvalidSortFieldError.for_field("x", allowed=frozenset({"created_at"}))
        assert isinstance(error, AppError)
        assert error.status_code == 422
        assert error.code == "INVALID_SORT_FIELD"

    def test_app_error_precedes_value_error_in_the_mro(self) -> None:
        """Exactly how Starlette resolves the handler for this exception."""
        mro = InvalidSortFieldError.__mro__
        assert mro.index(AppError) < mro.index(ValueError)

    def test_the_message_carries_no_internal_detail(self) -> None:
        """The message reaches the client verbatim, so it names only the field."""
        error = InvalidSortFieldError.for_field("ciphertext", allowed=frozenset({"created_at"}))
        assert error.message == "'ciphertext' is not a sortable field"


class TestPage:
    @pytest.mark.parametrize(
        ("total", "page_size", "expected"),
        [(101, 25, 5), (100, 25, 4), (0, 25, 0), (1, 25, 1)],
    )
    def test_total_pages(self, total: int, page_size: int, expected: int) -> None:
        assert Page(items=[], total=total, page=1, page_size=page_size).total_pages == expected

    def test_zero_page_size_does_not_divide_by_zero(self) -> None:
        assert Page(items=[], total=10, page=1, page_size=0).total_pages == 0


class TestSortParams:
    def test_direction(self) -> None:
        assert SortParams(field="x", order="desc").descending
        assert not SortParams(field="x", order="asc").descending
