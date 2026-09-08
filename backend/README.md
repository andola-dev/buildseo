# BuildSEO — backend

A multi-tenant SaaS backend for discovering, qualifying, managing and
submitting links to **free** online listing and directory sites.

FastAPI + PostgreSQL 16, fully asynchronous (SQLAlchemy 2.x AsyncIO over
asyncpg — there is no synchronous session anywhere in the application).

The architecture, the ERD, the RLS strategy, both state machines and the
endpoint inventory are documented in [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md).
This file is how to run it.

---

## What it does

1. **Discovers** candidate free directories and listing sites through pluggable
   providers (search APIs, a seed list, an AI-assisted provider).
2. **Qualifies** them: crawls the site, scores quality, relevance, spam risk
   and authority, and records *why* — a score a user has to trust is returned
   with its components and reasons.
3. **Creates opportunities** against a campaign and a client website, and moves
   them through a state machine.
4. **Generates listing copy** with the workspace's own AI provider, stores the
   draft, and requires a person to review it.
5. **Submits** — only after an explicit human approval, and only ever to a
   `FREE` publisher.
6. **Verifies** that the resulting link is live, and monitors it.

### What it deliberately does not do

These are product boundaries, not gaps:

- No paid link placements, paid directories, guest-post marketplaces, paid
  publishers, link buying, PBN management or automated outreach. Only
  `pricing_type = FREE` publishers may enter the submission workflow, enforced
  by the service **and** by a database trigger.
- No CAPTCHA solving, no anti-bot circumvention and no bypassing of publisher
  restrictions. When the submission adapter detects a CAPTCHA, a login wall, a
  bot challenge or terms prohibiting automation, it stops and hands the target
  to a human with the reason attached.
- No email of any kind at this stage: no verification, reset, invitation or
  notification email, and no SMTP configuration. Email is an identity field.
- No automatic submission at all in this MVP. The form adapter pre-flights a
  target and returns `BLOCKED_REQUIRES_MANUAL`; a person completes the
  submission.

---

## Requirements

- Python **3.12+**
- PostgreSQL **16+**
- Docker and Docker Compose (optional, but the fastest path)

---

## Quick start with Docker

```bash
cd backend
cp .env.example .env

# Generate the two real secrets. The app refuses to start outside local/test
# while either is still the placeholder.
python - <<'PY'
import base64, secrets, pathlib, re
env = pathlib.Path(".env")
text = env.read_text()
text = re.sub(r"^JWT_SECRET=.*$", f"JWT_SECRET={secrets.token_urlsafe(48)}", text, flags=re.M)
text = re.sub(
    r"^ENCRYPTION_KEY=.*$",
    f"ENCRYPTION_KEY={base64.b64encode(secrets.token_bytes(32)).decode()}",
    text,
    flags=re.M,
)
env.write_text(text)
PY

docker compose up --build
```

The stack brings up PostgreSQL, applies every migration, seeds the permission
catalog and serves the API on <http://localhost:8000>. Interactive docs are at
<http://localhost:8000/docs>.

`docker/postgres/init/00-create-app-role.sh` creates the runtime role during
first initialisation. That role is **`NOSUPERUSER` and `NOBYPASSRLS`**, which
is the whole point: a superuser bypasses Row-Level Security entirely, so the
application must never connect as one.

---

## Local development without Docker

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env      # then set JWT_SECRET and ENCRYPTION_KEY as above
```

Create the two roles and the database:

```sql
CREATE ROLE buildseo LOGIN PASSWORD 'buildseo' SUPERUSER;      -- owns the schema
CREATE ROLE buildseo_app LOGIN PASSWORD 'buildseo_app'
  NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;             -- the runtime role
CREATE DATABASE buildseo OWNER buildseo;
```

Then:

```bash
alembic upgrade head          # schema, RLS policies, grants
python -m scripts.seed        # permission catalog (never any secret)
uvicorn app.main:app --reload
```

Optionally bootstrap a first workspace. The password is read from
`SEED_OWNER_PASSWORD` or prompted for — never passed as a flag, where it would
land in the shell history and the process table:

```bash
python -m scripts.seed --owner-email you@example.com --workspace "Acme SEO"
```

Run the background worker in another terminal:

```bash
python -m app.workers.runner
```

---

## Configuration

Every setting is an environment variable, documented in
[`.env.example`](.env.example). `.env` is git-ignored and must never be
committed.

Two secrets have no default worth using:

| Variable | What it is | Generate with |
| --- | --- | --- |
| `JWT_SECRET` | Signs access tokens (HS256, pinned algorithm) | `openssl rand -base64 48` |
| `ENCRYPTION_KEY` | Master key wrapping every stored provider credential | `openssl rand -base64 32` |

`Settings.validate_production_hardening()` runs at startup and refuses to boot
outside `local`/`test` when a secret is still a placeholder or too short, when
`DEBUG` or `LOG_REQUEST_BODY` is on, or when CORS is `*`.

**Losing `ENCRYPTION_KEY` makes stored provider credentials unrecoverable.**
Rotate by adding a version and re-wrapping (`EnvelopeEncryptionService.rewrap`,
which never decrypts the secret itself), not by overwriting.

### Provider API keys are not configured here

BuildSEO is bring-your-own-key. Each workspace stores its own credentials
through `POST /api/v1/credentials`, and they are encrypted at rest with a
per-credential data key wrapped by `ENCRYPTION_KEY` and bound to that
workspace, that row and that provider. There is deliberately **no global
provider key**, and no endpoint that returns a stored secret — only a masked
hint such as `sk-****abcd`.

---

## Tests

Four suites, separated by what they need to run:

```bash
pytest tests/unit           # pure logic — no database, no web stack
pytest tests/integration    # real PostgreSQL, migrations applied from empty
pytest tests/security       # isolation, RBAC, tokens, credential leakage
pytest tests/api            # full stack over httpx ASGITransport
pytest                      # everything
```

The database suites build the schema by running **Alembic from empty**, so
"migrations apply cleanly from scratch" is asserted on every run rather than
being a separate thing to remember. They connect using `TEST_DATABASE_URL`
and `TEST_APP_DATABASE_URL`, which `tests/conftest.py` loads from
`.env.test` — committed, since it holds no secrets, just the address of a
scratch database that must never be the development one. Create that
database once:

```bash
createdb buildseo_test
psql -d buildseo -c "GRANT CONNECT ON DATABASE buildseo_test TO buildseo_app;"
psql -d buildseo_test -c "GRANT USAGE ON SCHEMA public TO buildseo_app; REVOKE CREATE ON SCHEMA public FROM PUBLIC;"
pytest
```

If your Postgres uses different roles or a different host, override
`TEST_DATABASE_URL`/`TEST_APP_DATABASE_URL` in your shell — an exported
value always wins over `.env.test`.

Isolation is asserted through the `NOBYPASSRLS` runtime role. Asserting it over
a superuser connection would prove nothing.

Markers: `unit`, `integration`, `security`, `api`.

Every branch push runs the same thing in CI
(`.github/workflows/backend-ci.yml`): a `lint` job for Ruff, Black and MyPy,
and a `test` job that stands up PostgreSQL 16, creates both roles, runs all
four suites, and finishes by downgrading every migration back to base. It also
asserts that `buildseo_app` cannot bypass RLS before running anything — a green
isolation suite over a privileged role would be a false green.

---

## Code quality

```bash
ruff check .
black --check .
mypy app
```

`pyproject.toml` holds the configuration: Ruff (including `S`/bandit,
`ASYNC` and `T20`), Black at 100 columns, and MyPy in strict mode over `app`.

---

## Migrations

Alembic is the **only** way the schema changes. Never modify a database by
hand — including production.

```bash
alembic revision -m "add x"     # then write the migration; autogenerate is a draft
alembic upgrade head
alembic downgrade -1
alembic current
```

Every revision has a working `downgrade`. Revision `0017` enables and **forces**
Row-Level Security on every tenant-owned table and then asserts completeness:
if a table with a `tenant_id` column lacks forced RLS and a policy, the
migration aborts rather than leaving a hole. Revision `0018` grants DML to the
runtime role, revokes `UPDATE`/`DELETE` on `audit_logs` and `ai_usage_records`
so the application cannot rewrite its own history, and revokes `CREATE` on
schema `public`.

---

## How tenant isolation works

Three independent layers, because relying on application code alone would mean
one missing `WHERE` clause is a cross-tenant data breach:

1. **PostgreSQL Row-Level Security.** Every tenant-owned table has RLS
   `ENABLE`d and `FORCE`d, with `USING` and `WITH CHECK` policies comparing
   `tenant_id` against `app.current_tenant_id`. A query with no `WHERE
   tenant_id` at all still only touches the active workspace's rows.
2. **A server-derived tenant context.** The active tenant is resolved from the
   authenticated user's *membership* and applied with
   `set_config('app.current_tenant_id', $1, true)` — transaction-local, so a
   pooled connection handed to the next request carries no tenant. A client can
   request a workspace; it can never set the context. No context means no rows
   (default deny), not all rows.
3. **Repository scoping.** `TenantRepository` takes `tenant_id` from
   `session.require_tenant_id()`, which raises if no membership was validated.
   Tenant-owned repositories accept no `tenant_id` argument at all, so a caller
   cannot pass the wrong one.

## How authorization works

Permission-based, never role-name-based. There is no
`if user.role == "admin"` anywhere; routes declare
`Depends(require_permission(Perm.PUBLISHER_CREATE))`. Permissions are resolved
per request from the database rather than cached in the token, so revoking a
role takes effect on the caller's next request instead of when their token
expires.

Fifty permission codes and five system roles (Owner, Admin, SEO Manager, SEO
Specialist, Viewer) are seeded per workspace, so a workspace can edit or extend
its own roles without affecting anyone else. The ladder nests strictly:
promoting a member never takes visibility away from them.

---

## Layout

```
app/
├── api/            routers (thin) and dependencies (auth, tenant, RBAC, pagination)
├── audit/          action codes, per-action metadata allow-lists, audit service
├── auth/           login, refresh rotation with reuse detection, sessions
├── campaigns/      campaign lifecycle
├── config/         settings and structured logging with redaction
├── core/           ids, crypto, security, HTTP client, pagination, exceptions
├── credentials/    BYOK storage, rotation, verification
├── db/             engine, tenant-aware session, tenant context, mixins
├── integrations/   AI, discovery, crawler, metrics, submission providers
├── models/         SQLAlchemy models
├── opportunities/  opportunity state machine and content generation
├── organizations/  client websites
├── publishers/     discovery, qualification, scoring
├── rbac/           permission catalog, role definitions, RBAC service
├── repositories/   data access (tenant-scoped by construction)
├── schemas/        Pydantic v2 request/response schemas
├── services/       the per-request service graph
├── submissions/    submission workflow and link verification
├── tenants/        workspace and membership administration
├── users/          profile and membership queries
└── workers/        PostgreSQL-backed queue, task registry, worker runner
```

92 endpoints across 15 routers. Every integration sits behind a Protocol —
`AIProvider`, `PublisherDiscoveryProvider`, `CrawlerProvider`,
`MetricsProvider`, `SubmissionProvider`, `LinkVerifier`, `TaskQueue`,
`RateLimiter`, `KeyProvider` — so browser automation, a third-party discovery
API or a real broker can be added later without touching the core.

---

## Background work

PostgreSQL is the queue for the MVP, which is a choice rather than a shortcut:
`SELECT … FOR UPDATE SKIP LOCKED` gives safe multi-worker claiming with nothing
extra to run or back up, and an enqueue is **transactional with the domain
change that caused it** — so a rolled-back request cannot leave an orphaned
job, a guarantee an external broker needs an outbox to match.

A worker reads the queue across tenants (it serves all of them) but runs each
handler inside a *separate* tenant-scoped session, so a handler is as confined
by RLS as an HTTP request is.

`TaskQueue` is a Protocol; Celery, Dramatiq, ARQ or Temporal can replace the
implementation when the volume justifies the operational cost.

---

## Operations

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Aggregate service health. No authentication. |
| `GET /health/live` | Liveness. Checks no dependency, so a transient database failure never triggers a restart. |
| `GET /health/ready` | Readiness. Verifies database connectivity; 503 removes the instance from load balancing. |

Logs are structured JSON with a request id, user id and tenant id bound per
request. Redaction happens **inside the logging stack**, so a password, token,
API key, encryption key or `Authorization` header cannot be logged even by a
caller that passes one to `logger.info`.
