"""Pagination, sorting and search query-parameter dependencies.

Page size is clamped to the configured maximum rather than rejected: a client
asking for 10,000 rows gets the maximum page instead of an error, which is
friendlier and still bounds the work the database does.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query

from app.api.dependencies.core import ResourcesDep
from app.core.pagination import PageParams, SortParams, clamp_page_size


async def get_page_params(
    resources: ResourcesDep,
    page: Annotated[int, Query(ge=1, le=100_000, description="1-based page number")] = 1,
    page_size: Annotated[
        int | None,
        Query(ge=1, description="Items per page; clamped to the configured maximum"),
    ] = None,
) -> PageParams:
    settings = resources.settings
    return PageParams(
        page=page,
        page_size=clamp_page_size(
            page_size, default=settings.default_page_size, maximum=settings.max_page_size
        ),
    )


async def get_sort_params(
    sort: Annotated[
        str | None,
        Query(
            max_length=64,
            description=(
                "Field to sort by. Each collection documents its sortable fields; "
                "anything else is rejected with 422."
            ),
        ),
    ] = None,
    order: Annotated[str, Query(pattern="^(asc|desc)$", description="Sort direction")] = "desc",
) -> SortParams:
    return SortParams(field=sort, order="asc" if order == "asc" else "desc")


PageParamsDep = Annotated[PageParams, Depends(get_page_params)]
SortParamsDep = Annotated[SortParams, Depends(get_sort_params)]

SearchQuery = Annotated[
    str | None,
    Query(
        alias="q",
        max_length=200,
        description="Free-text search over the collection's searchable fields",
    ),
]
