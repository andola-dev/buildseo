"""HTTP client fixtures.

The app is exercised through ``httpx.ASGITransport`` rather than a live server:
the full middleware, dependency and exception-handler stack runs, but with no
socket, so the tests stay fast and deterministic.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from fastapi import FastAPI

from app.bootstrap import AppResources
from app.config.settings import Settings
from app.main import create_app
from tests.fixtures.tenants import PASSWORD, TenantFixture


@pytest_asyncio.fixture
async def app(settings: Settings, resources: AppResources) -> FastAPI:
    """The real application, sharing the suite's engine and resources."""
    return create_app(settings, resources=resources)


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


async def login(
    client: httpx.AsyncClient, *, email: str, password: str = PASSWORD, tenant_id=None
) -> dict[str, str]:
    """Log in and return the token pair."""
    payload: dict[str, object] = {"email": email, "password": password}
    if tenant_id is not None:
        payload["tenant_id"] = str(tenant_id)
    response = await client.post("/api/v1/auth/login", json=payload)
    response.raise_for_status()
    return response.json()["data"]


def auth_headers(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest_asyncio.fixture
async def tenant_a_headers(client: httpx.AsyncClient, tenant_a: TenantFixture) -> dict[str, str]:
    """Authorisation headers for tenant A's owner, scoped to tenant A."""
    tokens = await login(client, email=tenant_a.owner.email, tenant_id=tenant_a.tenant_id)
    return auth_headers(tokens)


@pytest_asyncio.fixture
async def tenant_b_headers(client: httpx.AsyncClient, tenant_b: TenantFixture) -> dict[str, str]:
    tokens = await login(client, email=tenant_b.owner.email, tenant_id=tenant_b.tenant_id)
    return auth_headers(tokens)
