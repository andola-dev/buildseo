"""Repository base classes.

``TenantRepository`` derives ``tenant_id`` from the session's validated tenant
context rather than accepting it as an argument. That is deliberate: an
argument can be omitted, defaulted or passed the wrong value, whereas
:meth:`TenantAwareSession.require_tenant_id` raises if no membership was ever
validated. Combined with PostgreSQL RLS, a tenant-owned query is filtered
twice and cannot run unscoped at all.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Mapped
from sqlalchemy.sql.elements import ColumnElement

from app.core.exceptions import ResourceNotFoundError
from app.core.pagination import Page, PageParams, SortParams, resolve_sort
from app.db.base import Base
from app.db.session import TenantAwareSession

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Shared plumbing for global (non-tenant-owned) tables."""

    model: type[ModelT]
    #: Columns a client may sort by. Anything else is a 422, not a silent
    #: fallback, so a caller never believes it sorted when it did not.
    sortable_fields: frozenset[str] = frozenset({"created_at"})
    default_sort: str = "created_at"

    def __init__(self, session: TenantAwareSession) -> None:
        self.session = session

    # ------------------------------------------------------------- helpers --

    def _select(self) -> Select[tuple[ModelT]]:
        return select(self.model)

    def _order_by(self, statement: Select[Any], sort: SortParams | None) -> Select[Any]:
        """Apply a validated ``ORDER BY``, tie-broken by primary key.

        The ``id`` tie-breaker matters: without it, rows with equal sort values
        can appear on two pages or on none, because PostgreSQL makes no
        stability promise for an unordered remainder.
        """
        requested = sort.field if sort else None
        field = resolve_sort(requested, allowed=self.sortable_fields, default=self.default_sort)
        column: Mapped[Any] = getattr(self.model, field)
        descending = sort.descending if sort else True
        primary = self.model.id
        if descending:
            return statement.order_by(column.desc(), primary.desc())
        return statement.order_by(column.asc(), primary.asc())

    async def _paginate(
        self,
        statement: Select[tuple[ModelT]],
        *,
        page: PageParams,
        sort: SortParams | None = None,
    ) -> Page[ModelT]:
        """Run a count and a window over the same filtered statement.

        The count reuses the caller's filters via a subquery so the total can
        never disagree with the page contents.
        """
        count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
        total = int((await self.session.execute(count_statement)).scalar_one())

        windowed = self._order_by(statement, sort).offset(page.offset).limit(page.limit)
        rows = list((await self.session.execute(windowed)).scalars().all())
        return Page(items=rows, total=total, page=page.page, page_size=page.page_size)

    # ------------------------------------------------------------ mutations --

    def add(self, entity: ModelT) -> ModelT:
        """Stage an insert. The request's unit of work commits it."""
        self.session.add(entity)
        return entity

    async def flush(self) -> None:
        """Force pending SQL now, to surface constraint violations early."""
        await self.session.flush()

    async def delete(self, entity: ModelT) -> None:
        await self.session.delete(entity)


class TenantRepository(BaseRepository[ModelT]):
    """Base class for every tenant-owned table."""

    @property
    def tenant_id(self) -> UUID:
        """The validated active tenant. Raises if none was established."""
        return self.session.require_tenant_id()

    def _select(self) -> Select[tuple[ModelT]]:
        """Every read starts already filtered by tenant."""
        return select(self.model).where(self.model.tenant_id == self.tenant_id)  # type: ignore[attr-defined]

    async def get(self, entity_id: UUID) -> ModelT | None:
        result = await self.session.execute(self._select().where(self.model.id == entity_id))  # type: ignore[attr-defined]
        return result.scalar_one_or_none()

    async def get_or_raise(self, entity_id: UUID, *, resource: str) -> ModelT:
        """Fetch or raise 404.

        A row belonging to another tenant is indistinguishable from one that
        does not exist — deliberately, so a caller cannot probe another
        tenant's identifier space by comparing 403 against 404.
        """
        entity = await self.get(entity_id)
        if entity is None:
            raise ResourceNotFoundError.for_resource(resource, entity_id)
        return entity

    async def list_page(
        self,
        *,
        page: PageParams,
        sort: SortParams | None = None,
        filters: Sequence[ColumnElement[bool]] = (),
    ) -> Page[ModelT]:
        statement = self._select()
        for condition in filters:
            statement = statement.where(condition)
        return await self._paginate(statement, page=page, sort=sort)

    async def count(self, filters: Sequence[ColumnElement[bool]] = ()) -> int:
        statement = self._select()
        for condition in filters:
            statement = statement.where(condition)
        count_statement = select(func.count()).select_from(statement.subquery())
        return int((await self.session.execute(count_statement)).scalar_one())

    async def exists(self, filters: Sequence[ColumnElement[bool]]) -> bool:
        statement = self._select()
        for condition in filters:
            statement = statement.where(condition)
        result = await self.session.execute(select(statement.exists()))
        return bool(result.scalar_one())

    def new(self, **values: Any) -> ModelT:
        """Instantiate a row with ``tenant_id`` filled in from the session.

        Callers never set ``tenant_id`` themselves, so they cannot set it
        wrongly; RLS's ``WITH CHECK`` would reject it anyway.
        """
        values.pop("tenant_id", None)
        entity = self.model(tenant_id=self.tenant_id, **values)
        self.session.add(entity)
        return entity

    async def delete_by_id(self, entity_id: UUID) -> int:
        """Tenant-filtered delete. Returns the number of rows removed."""
        statement = (
            delete(self.model)
            .where(self.model.tenant_id == self.tenant_id)  # type: ignore[attr-defined]
            .where(self.model.id == entity_id)  # type: ignore[attr-defined]
        )
        result = await self.session.execute(statement)
        return int(result.rowcount or 0)
