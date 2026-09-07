# syntax=docker/dockerfile:1.7

# --------------------------------------------------------------------------- #
# Builder — install dependencies into an isolated virtualenv
# --------------------------------------------------------------------------- #
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# build-essential is needed for any wheel without a manylinux build; it stays
# in this stage only, so the runtime image carries no compiler.
RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy only the dependency manifest first so the layer caches across code edits.
COPY pyproject.toml README.md ./
COPY app/__init__.py app/__init__.py
RUN pip install --upgrade pip setuptools wheel && pip install ".[dev]"

# --------------------------------------------------------------------------- #
# Runtime — slim, non-root, no build tooling
# --------------------------------------------------------------------------- #
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_ENV=production

RUN apt-get update \
    && apt-get install --no-install-recommends -y curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1001 buildseo \
    && useradd --system --uid 1001 --gid buildseo --create-home buildseo

COPY --from=builder /opt/venv /opt/venv

WORKDIR /srv/app
COPY --chown=buildseo:buildseo alembic.ini pyproject.toml README.md ./
COPY --chown=buildseo:buildseo app ./app
COPY --chown=buildseo:buildseo migrations ./migrations
COPY --chown=buildseo:buildseo scripts ./scripts

# Never run application code as root.
USER buildseo

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health/live || exit 1

# proxy-headers lets the app see the real client scheme/address behind a
# load balancer; forwarded-allow-ips is narrowed at deploy time.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--proxy-headers", \
     "--no-access-log"]
