"""Root test configuration.

Deliberately imports nothing heavy. Database and HTTP fixtures live in the
per-suite ``conftest.py`` files (``tests/integration``, ``tests/api``,
``tests/security``) so ``tests/unit`` can run without a database and without
the web stack — which is what keeps the pure-logic tests fast and usable as a
pre-commit check.
"""

from __future__ import annotations

import os

import pytest

# Never let a test run pick up a developer's real .env.
os.environ.setdefault("APP_ENV", "test")


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"
