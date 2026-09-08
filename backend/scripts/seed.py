"""Seed the global permission catalog (and, optionally, a first workspace).

What this script does and does not do is the important part.

**It seeds reference data only.** The permission catalog is the platform's
authorization vocabulary: ``require_permission`` compares against it, the
``/permissions`` endpoint publishes it, and every seeded role is defined in
terms of it. It is global rather than tenant-owned, so it has to exist before
any workspace can be created — ``TenantService.seed_system_roles`` refuses with
``PERMISSION_CATALOG_INCOMPLETE`` if it does not.

**It never seeds a secret.** No API key, no provider credential, no encryption
key, no default password. The optional ``--owner-email`` bootstrap exists so a
fresh deployment has a way in at all. Its password is **not** a flag — there is
deliberately no ``--owner-password``, because a password on the command line
lands in the shell history and the process table. It comes from
``SEED_OWNER_PASSWORD`` or an interactive prompt, is validated against the same
policy the API applies, and is stored only as an Argon2id hash. There is no
default account and no fallback credential anywhere in this file.

Idempotent: run it on every deploy. Existing permissions are updated in place
if their description changed and left alone otherwise; an existing user or
workspace is reported and skipped rather than modified.

Usage::

    python -m scripts.seed                          # permissions only
    python -m scripts.seed --owner-email you@example.com --workspace "Acme SEO"

The owner password comes from ``SEED_OWNER_PASSWORD`` if set, and is prompted
for interactively otherwise. It is never passed on the command line, where it
would land in the shell history and the process table.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys

from sqlalchemy import select

from app.bootstrap import build_resources
from app.config.logging import configure_logging, get_logger
from app.config.settings import Settings, get_settings
from app.core.security.password_policy import PasswordPolicy
from app.db.session import session_scope
from app.models.rbac import Permission
from app.models.users import User
from app.rbac.catalog import PERMISSION_CATALOG
from app.services.factory import ServiceFactory

logger = get_logger(__name__)

#: Read from the environment rather than a flag, so it never reaches the
#: process table or the shell history.
PASSWORD_ENV_VAR = "SEED_OWNER_PASSWORD"  # noqa: S105 - a variable name, not a secret


async def seed_permissions(settings: Settings) -> tuple[int, int]:
    """Insert or refresh every catalog entry. Returns (created, updated).

    Runs as the migration/owner role via ``alembic_url``: ``permissions`` is a
    global table outside RLS, and seeding it needs no tenant context.
    """
    resources = build_resources(settings, engine=None)
    try:
        created = 0
        updated = 0
        async with session_scope(resources.session_factory) as session:
            existing = {
                row.code: row for row in (await session.execute(select(Permission))).scalars().all()
            }
            for spec in PERMISSION_CATALOG:
                current = existing.get(spec.code)
                if current is None:
                    session.add(
                        Permission(
                            code=spec.code,
                            resource=spec.resource,
                            action=spec.action,
                            description=spec.description,
                        )
                    )
                    created += 1
                elif current.description != spec.description:
                    # Wording changes are safe to apply; the code is the
                    # identity and is never rewritten.
                    current.description = spec.description
                    updated += 1
        return created, updated
    finally:
        await resources.aclose()


async def seed_owner(settings: Settings, *, email: str, password: str, workspace_name: str) -> None:
    """Create a first user and workspace, if they do not already exist.

    The workspace's five system roles are seeded by ``TenantService``, so this
    goes through the real service rather than writing rows directly — the
    ordering it enforces (insert tenant, establish tenant context, then insert
    tenant-owned rows) is exactly what RLS requires.
    """
    resources = build_resources(settings, engine=None)
    try:
        async with session_scope(resources.session_factory) as session:
            normalized = email.strip().lower()
            existing = (
                await session.execute(select(User).where(User.email == normalized))
            ).scalar_one_or_none()
            if existing is not None:
                logger.info("owner already exists; skipping", extra={"email": normalized})
                return

            user = User(
                email=normalized,
                password_hash=resources.password_hasher.hash(password),
                is_active=True,
            )
            session.add(user)
            await session.flush()

            services = ServiceFactory(session=session, resources=resources)
            tenant, _ = await services.tenant_service.create_tenant(
                name=workspace_name, slug=None, owner=user
            )
            logger.info(
                "workspace seeded",
                extra={"tenant_slug": tenant.slug, "tenant_id": str(tenant.id)},
            )
    finally:
        await resources.aclose()


def _read_password(email: str) -> str:
    """Take the owner password from the environment, or prompt for it."""
    from_env = os.environ.get(PASSWORD_ENV_VAR)
    if from_env:
        return from_env
    if not sys.stdin.isatty():
        raise SystemExit(
            f"No password available: set {PASSWORD_ENV_VAR} or run this interactively."
        )
    first = getpass.getpass(f"Password for {email}: ")
    second = getpass.getpass("Repeat: ")
    if first != second:
        raise SystemExit("Passwords did not match.")
    return first


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Seed the permission catalog. Optionally bootstrap a first owner and "
            "workspace. Never seeds API keys, provider credentials or default passwords."
        )
    )
    parser.add_argument(
        "--owner-email",
        help=(
            "Create this user as the owner of a first workspace, if absent. "
            "The password is read from SEED_OWNER_PASSWORD, or prompted for; "
            "it is deliberately not a flag, so it stays out of the shell "
            "history and the process table."
        ),
    )
    parser.add_argument(
        "--workspace",
        default="My Workspace",
        help="Name of the workspace created alongside --owner-email.",
    )
    return parser.parse_args(argv)


async def _amain(argv: list[str] | None = None) -> int:
    arguments = _parse_args(argv)
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        json_output=settings.log_json,
        service=f"{settings.app_name} seed",
        environment=settings.app_env,
    )

    # Seeding writes reference data, which the runtime role may not be allowed
    # to insert; use the migration role the same way Alembic does.
    seeding_settings = settings.model_copy(update={"database_url": settings.alembic_url})

    created, updated = await seed_permissions(seeding_settings)
    logger.info(
        "permission catalog seeded",
        extra={
            "permissions_created": created,
            "permissions_updated": updated,
            "total": len(PERMISSION_CATALOG),
        },
    )

    if arguments.owner_email:
        password = _read_password(arguments.owner_email)
        # The same policy the API applies, so a seeded account is no weaker
        # than a registered one.
        problems = PasswordPolicy().violations(password, personal_data=(arguments.owner_email,))
        if problems:
            raise SystemExit("The owner password " + "; ".join(problems) + ".")
        await seed_owner(
            seeding_settings,
            email=arguments.owner_email,
            password=password,
            workspace_name=arguments.workspace,
        )

    return 0


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())
