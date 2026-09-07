"""API-suite fixtures."""

pytest_plugins = [
    "tests.fixtures.database",
    "tests.fixtures.tenants",
    "tests.fixtures.api",
]
