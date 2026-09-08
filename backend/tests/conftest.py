"""Root test configuration.

Deliberately imports nothing heavy. Database and HTTP fixtures live in the
per-suite ``conftest.py`` files (``tests/integration``, ``tests/api``,
``tests/security``) so ``tests/unit`` can run without a database and without
the web stack — which is what keeps the pure-logic tests fast and usable as a
pre-commit check.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Never let a test run pick up a developer's real .env — only the test
# database URLs below, which point at a scratch database that is never the
# development one. load_dotenv defaults to not overriding already-exported
# vars, so a CI-provided TEST_DATABASE_URL still wins over this file.
load_dotenv(Path(__file__).parent.parent / ".env.test")
os.environ.setdefault("APP_ENV", "test")

# asyncpg is incompatible with Windows' default ProactorEventLoop (connection
# cleanup raises AttributeError / "Event loop is closed" once a session-scoped
# engine outlives a single test). The selector loop doesn't have this problem
# and is what every other platform uses by default.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"
