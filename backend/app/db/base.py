"""Declarative base and metadata conventions.

An explicit naming convention means every constraint and index gets a
deterministic name, which is what makes Alembic autogenerate produce stable,
reviewable migrations and lets a downgrade drop exactly what an upgrade
created.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class for every ORM model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    def __repr__(self) -> str:
        """Identity-only repr. Never dumps column values, which could include
        ciphertext or a password hash into a log line."""
        identifier = getattr(self, "id", None)
        return f"<{type(self).__name__} id={identifier}>"

    def to_dict(self, *, exclude: frozenset[str] = frozenset()) -> dict[str, Any]:
        """Column values as a plain dict, for audit metadata construction.

        Callers must pass ``exclude`` for any sensitive column; the audit
        service keeps its own allow-lists rather than relying on this.
        """
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
            if column.name not in exclude
        }
