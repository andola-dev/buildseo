# BuildSEO — Free Listing Discovery & Submission Platform

**Backend Architecture Specification**

BuildSEO is a multi-tenant SaaS backend for discovering, qualifying, managing and
submitting links to **free** online listing/directory sites. This document is the
architectural contract the implementation follows. It is written before the code and
is the reference for every design decision in `backend/`.

---

## 1. Architecture Overview

### 1.1 Shape of the system

A **modular monolith**: one FastAPI application composed of domain modules with
explicit boundaries, one PostgreSQL database, and a worker process that runs the same
codebase against a database-backed task queue.

```
                       ┌──────────────────────────────────────────┐
   HTTP client ───────▶ │  FastAPI ASGI app (app.main)            │
                       │  ┌────────────────────────────────────┐  │
                       │  │ Middleware                         │  │
                       │  │  request-id → logging → rate-limit │  │
                       │  └────────────────────────────────────┘  │
                       │  ┌────────────────────────────────────┐  │
                       │  │ api/v1 routers  (thin)             │  │
                       │  └──────────────┬─────────────────────┘  │
                       │  ┌──────────────▼─────────────────────┐  │
                       │  │ api/dependencies                   │  │
                       │  │  principal → membership → RBAC →   │  │
                       │  │  tenant-scoped DB session          │  │
                       │  └──────────────┬─────────────────────┘  │
                       │  ┌──────────────▼─────────────────────┐  │
                       │  │ services  (business rules)         │  │
                       │  └──────────────┬─────────────────────┘  │
                       │  ┌──────────────▼─────────────────────┐  │
                       │  │ repositories (tenant-filtered SQL) │  │
                       │  └──────────────┬─────────────────────┘  │
                       └─────────────────┼────────────────────────┘
                                         │ asyncpg (SET LOCAL app.current_tenant_id)
                       ┌─────────────────▼────────────────────────┐
                       │ PostgreSQL 16 — Row-Level Security       │
                       └─────────────────▲────────────────────────┘
                                         │
   ┌─────────────────────────────────────┴────────────────────────┐
   │ worker process (app.workers.runner)                          │
   │  claims jobs FOR UPDATE SKIP LOCKED, runs task handlers      │
   │  under the job's tenant context                              │
   └──────────────────────────────────────────────────────────────┘
                                         │
                       ┌─────────────────▼────────────────────────┐
                       │ Provider abstractions (all BYOK)         │
                       │  AIProvider · DiscoveryProvider ·        │
                       │  CrawlerProvider · SubmissionProvider ·  │
                       │  MetricsProvider                         │
                       └──────────────────────────────────────────┘
```

### 1.2 Layering rules

`Router → Service → Repository → Database`. Enforced by convention and review:

| Layer | May depend on | Never does |
|---|---|---|
| `api/v1` routers | schemas, dependencies, services | business logic, SQL, direct model mutation |
| `api/dependencies` | core, auth, rbac, db | domain services beyond identity/authz |
| `services` | repositories, other services, providers, core | HTTP concerns, `Request`, `HTTPException` |
| `repositories` | models, db session | business rules, provider calls |
| `providers` | core http client, credentials | database access |

Services raise **domain exceptions** (`app/core/exceptions.py`). A single exception
handler set maps them to HTTP status codes and the error envelope. Routers never
construct `HTTPException` for domain outcomes.

### 1.3 Cross-cutting concerns

| Concern | Mechanism |
|---|---|
| Configuration | `pydantic-settings`, `app/config/settings.py`, env only |
| Logging | `structlog`-style JSON via stdlib logging, contextvars carry `request_id`/`user_id`/`tenant_id`, redaction filter strips secrets |
| Errors | domain exceptions + `app/core/error_handlers.py` |
| Tenant context | `TenantAwareSession` sets `app.current_tenant_id` / `app.current_user_id` per transaction |
| Authorization | permission-based dependency `require_permission("publisher.create")` |
| Idempotency | `Idempotency-Key` header → `idempotency_keys` table + natural unique constraints |
| Background work | `TaskQueue` protocol; `PostgresTaskQueue` default, `InMemoryTaskQueue` in tests |
| Rate limiting | `RateLimiter` protocol; in-memory token bucket default, Redis-ready |
| Outbound HTTP | one shared pooled `httpx.AsyncClient` per app lifespan, wrapped by `SafeHttpClient` |

### 1.4 Decision priority

Security → Tenant isolation → Correctness → Maintainability → Performance → Convenience.

Consequences of that ordering, applied throughout:

- RLS is `FORCE`d, and the runtime database role is `NOBYPASSRLS`, so a missing
  application-level `WHERE tenant_id = …` cannot leak data.
- Credentials are envelope-encrypted and never leave the service layer in plaintext;
  no schema exposes a decrypted value.
- Default-deny: no tenant context ⇒ zero rows, not all rows.
- Only `pricing_type = FREE` publishers can enter a submission workflow, checked in
  the service layer **and** by a database constraint on the submission path.

---

## 2. Folder Structure

```
backend/
├── app/
│   ├── main.py                     # app factory, lifespan, middleware, routers
│   ├── config/
│   │   ├── settings.py             # pydantic-settings Settings + get_settings()
│   │   └── logging.py              # JSON/console logging config, redaction
│   ├── core/
│   │   ├── context.py              # contextvars: request_id, user_id, tenant_id
│   │   ├── exceptions.py           # AuthenticationError, TenantAccessError, …
│   │   ├── error_handlers.py       # exception → error envelope
│   │   ├── responses.py            # data/meta envelope helpers
│   │   ├── pagination.py           # PageParams, SortParams, Page[T]
│   │   ├── http_client.py          # pooled async HTTP client + retries + size caps
│   │   ├── rate_limit.py           # RateLimiter protocol + in-memory bucket
│   │   ├── crypto/
│   │   │   ├── keys.py             # KeyProvider protocol, EnvMasterKeyProvider
│   │   │   └── envelope.py         # AES-256-GCM envelope encryption service
│   │   ├── security/
│   │   │   ├── password.py         # Argon2id hashing + strength policy
│   │   │   └── tokens.py           # JWT encode/decode, opaque refresh tokens
│   │   ├── ids.py                  # UUIDv7 generation
│   │   ├── domains.py              # domain/URL normalization
│   │   └── idempotency.py          # idempotency key handling
│   ├── db/
│   │   ├── base.py                 # DeclarativeBase, naming convention
│   │   ├── mixins.py               # UUIDPk, Timestamps, TenantOwned
│   │   ├── session.py              # engine, sessionmaker, TenantAwareSession
│   │   ├── context.py              # set/reset tenant GUCs
│   │   └── types.py                # reusable column types
│   ├── models/                     # SQLAlchemy 2.x models (single import surface)
│   ├── schemas/                    # Pydantic v2 request/response schemas
│   ├── repositories/               # tenant-filtered data access
│   ├── services/                   # business logic
│   ├── api/
│   │   ├── router.py               # /api/v1 aggregation
│   │   ├── dependencies/           # auth, tenant, rbac, pagination, services
│   │   └── v1/                     # one module per resource
│   ├── auth/                       # login, refresh rotation, sessions
│   ├── rbac/                       # permission catalog, role defaults, checks
│   ├── tenants/                    # tenant + membership domain
│   ├── users/
│   ├── organizations/              # client websites (tenant's client projects)
│   ├── publishers/                 # publisher domain + discovery + qualification
│   ├── opportunities/
│   ├── submissions/                # workflow state machine + providers
│   ├── campaigns/
│   ├── credentials/                # BYOK credential storage
│   ├── integrations/               # provider abstractions & implementations
│   │   ├── ai/                     # AIProvider + OpenAI/Anthropic/Gemini/OpenRouter
│   │   ├── discovery/              # PublisherDiscoveryProvider implementations
│   │   ├── crawler/                # CrawlerProvider implementations
│   │   ├── metrics/                # SEO metrics providers
│   │   └── submission/             # SubmissionProvider implementations
│   ├── audit/                      # audit log service
│   └── workers/                    # TaskQueue protocol, registry, runner, tasks
├── migrations/                     # Alembic (versions/ 001…017)
├── tests/
│   ├── unit/                       # pure logic: crypto, tokens, scoring, domains
│   ├── integration/                # DB, repositories, RLS, tenant isolation
│   ├── api/                        # httpx ASGI transport end-to-end
│   └── security/                   # cross-tenant, RBAC, token, leakage tests
├── scripts/                        # seed, create_app_role, dev helpers
├── docker/postgres/init/           # app-role bootstrap for compose
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── alembic.ini
├── .env.example
└── README.md
```

---

## 3. Database ERD

```mermaid
erDiagram
    users ||--o{ tenant_memberships : "has"
    tenants ||--o{ tenant_memberships : "has"
    users ||--o{ refresh_sessions : "owns"
    tenants ||--o{ roles : "defines"
    roles ||--o{ role_permissions : "grants"
    permissions ||--o{ role_permissions : "granted by"
    tenant_memberships ||--o{ membership_roles : "assigned"
    roles ||--o{ membership_roles : "assigned to"

    tenants ||--o{ client_websites : "owns"
    client_websites ||--o{ campaigns : "targets"
    tenants ||--o{ campaigns : "owns"
    tenants ||--o{ publishers : "owns"
    campaigns ||--o{ opportunities : "contains"
    publishers ||--o{ opportunities : "sourced from"
    opportunities ||--o| submissions : "results in"
    campaigns ||--o{ submissions : "belongs to"
    opportunities ||--o{ generated_contents : "drafts"

    tenants ||--o{ credentials : "stores"
    credentials ||--o{ tenant_ai_configs : "used by"
    tenants ||--o{ tenant_ai_configs : "configures"
    tenants ||--o{ ai_usage_records : "accrues"
    tenants ||--o{ audit_logs : "records"
    tenants ||--o{ jobs : "enqueues"
    tenants ||--o{ idempotency_keys : "dedupes"
    tenants ||--o{ discovery_runs : "executes"
    discovery_runs ||--o{ publishers : "discovers"

    users {
        uuid   id PK
        citext email UK
        text   password_hash
        text   first_name
        text   last_name
        bool   is_active
        bool   is_verified
        bool   is_superuser
        ts     last_login_at
        ts     created_at
        ts     updated_at
    }

    tenants {
        uuid id PK
        text name
        text slug UK
        text status
        jsonb settings
        uuid created_by_user_id FK
        ts   created_at
        ts   updated_at
    }

    tenant_memberships {
        uuid id PK
        uuid tenant_id FK
        uuid user_id FK
        text status
        bool is_owner
        ts   created_at
        ts   updated_at
    }

    roles {
        uuid id PK
        uuid tenant_id FK
        text slug
        text name
        text description
        bool is_system
        ts   created_at
        ts   updated_at
    }

    permissions {
        uuid id PK
        text code UK
        text resource
        text action
        text description
    }

    role_permissions {
        uuid id PK
        uuid tenant_id FK
        uuid role_id FK
        uuid permission_id FK
    }

    membership_roles {
        uuid id PK
        uuid tenant_id FK
        uuid membership_id FK
        uuid role_id FK
    }

    refresh_sessions {
        uuid id PK
        uuid user_id FK
        uuid family_id
        text token_hash UK
        uuid active_tenant_id
        text user_agent
        inet ip_address
        bool revoked
        text revoked_reason
        ts   expires_at
        ts   last_used_at
        ts   created_at
    }

    client_websites {
        uuid id PK
        uuid tenant_id FK
        text name
        text domain
        text normalized_domain
        text website_url
        text description
        text industry
        text target_country
        jsonb target_countries
        text target_language
        text status
        ts   created_at
        ts   updated_at
    }

    campaigns {
        uuid id PK
        uuid tenant_id FK
        uuid client_website_id FK
        text name
        text description
        text status
        text target_country
        text target_language
        numeric budget
        bool free_only
        int  target_link_count
        date start_date
        date end_date
        ts   created_at
        ts   updated_at
    }

    publishers {
        uuid id PK
        uuid tenant_id FK
        text domain
        text normalized_domain
        text website_url
        text name
        text description
        text category
        text country
        text language
        text submission_url
        text contact_url
        text submission_method
        text pricing_type
        text link_type
        bool dofollow_supported
        bool nofollow_supported
        text status
        numeric quality_score
        numeric relevance_score
        numeric spam_score
        bigint organic_traffic
        numeric authority_score
        jsonb signals
        uuid discovery_run_id FK
        ts   last_checked_at
        ts   created_at
        ts   updated_at
    }

    opportunities {
        uuid id PK
        uuid tenant_id FK
        uuid campaign_id FK
        uuid publisher_id FK
        text opportunity_type
        text target_url
        text suggested_anchor
        text suggested_title
        text suggested_description
        text category
        text status
        numeric qualification_score
        int  priority
        text submission_url
        ts   discovered_at
        ts   qualified_at
        ts   created_at
        ts   updated_at
    }

    submissions {
        uuid id PK
        uuid tenant_id FK
        uuid campaign_id FK
        uuid opportunity_id FK
        text status
        text submitted_url
        text target_url
        text anchor_text
        text submitted_title
        text submitted_description
        text submission_method
        uuid approved_by_user_id FK
        ts   approved_at
        ts   submitted_at
        ts   published_at
        ts   verified_at
        text failure_reason
        text notes
        ts   created_at
        ts   updated_at
    }

    generated_contents {
        uuid id PK
        uuid tenant_id FK
        uuid opportunity_id FK
        text content_status
        jsonb generated_content
        text ai_provider
        text ai_model
        uuid reviewed_by_user_id FK
        ts   generation_timestamp
        ts   reviewed_at
        ts   created_at
        ts   updated_at
    }

    credentials {
        uuid id PK
        uuid tenant_id FK
        text provider
        text provider_type
        text label
        text status
        text masked_hint
        bytea ciphertext
        bytea nonce
        bytea encrypted_dek
        bytea dek_nonce
        int  key_version
        jsonb metadata
        ts   last_verified_at
        ts   created_at
        ts   updated_at
    }

    tenant_ai_configs {
        uuid id PK
        uuid tenant_id FK
        text purpose
        text provider
        text model
        uuid credential_id FK
        jsonb parameters
        bool is_default
        ts   created_at
        ts   updated_at
    }

    ai_usage_records {
        uuid id PK
        uuid tenant_id FK
        text provider
        text model
        text operation
        int  input_tokens
        int  output_tokens
        numeric estimated_cost
        text request_id
        text status
        ts   created_at
    }

    audit_logs {
        uuid id PK
        uuid tenant_id FK
        uuid user_id FK
        text action
        text resource_type
        text resource_id
        jsonb metadata
        inet ip_address
        text user_agent
        ts   created_at
    }

    jobs {
        uuid id PK
        uuid tenant_id FK
        text task_name
        jsonb payload
        text status
        int  attempts
        int  max_attempts
        ts   run_at
        ts   started_at
        ts   finished_at
        text last_error
        ts   created_at
        ts   updated_at
    }

    discovery_runs {
        uuid id PK
        uuid tenant_id FK
        uuid campaign_id FK
        text provider
        jsonb query
        text status
        int  results_found
        int  publishers_created
        text error
        ts   created_at
        ts   updated_at
    }

    idempotency_keys {
        uuid id PK
        uuid tenant_id FK
        text key
        text endpoint
        text request_hash
        int  response_status
        jsonb response_body
        text resource_id
        ts   created_at
    }
```

---

## 4. Entity Relationship Explanation

**Identity is global; everything else is tenant-owned.**

- `users` and `tenants` are *global* tables. A user is one human with one login,
  independent of how many workspaces they can reach. `permissions` is a global,
  immutable catalog of capability codes.
- `tenant_memberships` is the bridge and the **only** authority on whether a user may
  touch a tenant. It carries `status` (`ACTIVE`, `SUSPENDED`, `INVITED`) and
  `is_owner`. `UNIQUE (tenant_id, user_id)`.
- `roles` are **per tenant** (`tenant_id NOT NULL`). Each new tenant is seeded with
  the five system roles (`owner`, `admin`, `seo_manager`, `seo_specialist`, `viewer`,
  `is_system = true`). Custom roles are just non-system rows, so custom RBAC needs no
  schema change. `UNIQUE (tenant_id, slug)`.
- `role_permissions` maps a tenant's role to catalog permissions.
  `membership_roles` assigns roles to a membership — a user can hold several roles in
  one tenant; effective permissions are the union.
- `refresh_sessions` is the server-side session/token-family store. It holds only a
  SHA-256 hash of the opaque refresh token, never the token.

**The SEO domain.**

- `client_websites` are the tenant's own clients/projects — the things being promoted.
- `campaigns` belong to exactly one `client_website` (and therefore one tenant) and
  carry link goals. `free_only` defaults to `true` and, for the MVP, is constrained to
  `true`.
- `publishers` are candidate listing sites, owned per tenant so one tenant's research,
  scores and notes never bleed into another's. `normalized_domain` is the canonical
  identity used for de-duplication; `UNIQUE (tenant_id, normalized_domain)`.
- `opportunities` are the join of "this campaign wants a link" × "this publisher may
  accept one", with lifecycle status and scores.
  `UNIQUE (tenant_id, campaign_id, publisher_id, target_url)` prevents duplicates from
  retries or re-runs.
- `submissions` record the act of submitting one opportunity.
  `UNIQUE (tenant_id, opportunity_id)` on live rows keeps one active submission per
  opportunity (terminal `FAILED`/`REJECTED` rows are excluded via a partial index so a
  retry is possible).
- `generated_contents` stores AI-drafted listing copy **before** submission, with
  provider/model/timestamp, so a human reviews an auditable artifact.

**BYOK and operations.**

- `credentials` holds per-tenant, per-provider secrets as envelope-encrypted bytes.
- `tenant_ai_configs` selects provider + model + credential per *purpose*
  (`content_generation`, `discovery`, `qualification`, `embedding`) so the business
  layer asks for a purpose, not a vendor.
- `ai_usage_records`, `audit_logs`, `jobs`, `discovery_runs` and `idempotency_keys` are
  tenant-owned operational tables.

---

## 5. RLS Strategy

### 5.1 Threat model

Assume the application will one day contain a query that forgets `WHERE tenant_id = …`.
PostgreSQL must still refuse to return, modify or delete another tenant's rows.

### 5.2 Roles

| Role | Purpose | RLS |
|---|---|---|
| `buildseo` (compose `POSTGRES_USER`) | owns schema, runs Alembic | superuser in dev — bypasses RLS, so **never** used by the API |
| `buildseo_app` | the API and worker runtime role | `NOSUPERUSER`, `NOBYPASSRLS` — fully subject to policies |

`FORCE ROW LEVEL SECURITY` is set on every protected table so that even the table
*owner* is subject to policies. This closes the "dev runs as owner" hole; the only
remaining bypass is a cluster superuser, which the runtime never is.

### 5.3 Context propagation

Two session GUCs, set with `set_config(name, value, is_local => true)` so PostgreSQL
discards them at transaction end — the mechanism that prevents leakage across pooled
connections:

```
app.current_tenant_id   -- active tenant, derived from validated membership
app.current_user_id     -- authenticated user
```

Both are **server-derived**. `app.current_tenant_id` comes from a
`tenant_memberships` row looked up for the authenticated `sub` claim; a tenant id in a
request body or header is only ever a *candidate* that must survive membership
validation. The value is passed as a bound parameter, never interpolated.

`TenantAwareSession` (a small `AsyncSession` subclass) remembers the context and
re-applies it after any `commit()`, so a mid-request commit cannot silently continue
in an unscoped transaction.

Helper functions in SQL:

```sql
CREATE FUNCTION app_current_tenant_id() RETURNS uuid LANGUAGE sql STABLE AS $$
  SELECT nullif(current_setting('app.current_tenant_id', true), '')::uuid $$;
CREATE FUNCTION app_current_user_id() RETURNS uuid LANGUAGE sql STABLE AS $$
  SELECT nullif(current_setting('app.current_user_id', true), '')::uuid $$;
```

### 5.4 Policy shape

For every tenant-owned table:

```sql
ALTER TABLE publishers ENABLE ROW LEVEL SECURITY;
ALTER TABLE publishers FORCE ROW LEVEL SECURITY;

CREATE POLICY publishers_tenant_isolation ON publishers
  USING      (tenant_id = app_current_tenant_id())
  WITH CHECK (tenant_id = app_current_tenant_id());
```

- `USING` filters `SELECT`/`UPDATE`/`DELETE`.
- `WITH CHECK` blocks `INSERT`/`UPDATE` that would write another tenant's id — so a
  tenant cannot *plant* a row in another tenant either.
- Unset context ⇒ `app_current_tenant_id()` is `NULL` ⇒ predicate is `NULL` ⇒ **no
  rows, default deny**.

`tenant_memberships` needs one extra permissive policy, because "which tenants may I
enter?" is answered *before* a tenant is chosen:

```sql
CREATE POLICY memberships_self_access ON tenant_memberships
  USING (user_id = app_current_user_id());
```

Permissive policies OR together: a membership row is visible if it belongs to the
current tenant **or** to the current user.

### 5.5 Deliberately excluded tables

`users`, `tenants`, `permissions`, `refresh_sessions` carry no `tenant_id` and are not
tenant-owned. They must be reachable before a tenant is chosen (login, token refresh,
tenant list, tenant creation), so putting them behind a tenant predicate would break
authentication rather than protect it. They are protected by:

- application-level scoping in repositories (`users` are only ever listed through a
  membership join for the active tenant),
- membership validation in dependencies,
- `refresh_sessions` rows keyed to `user_id` and matched by token hash.

This exclusion is a conscious, documented boundary — not an oversight. Every table
with a `tenant_id` column is covered, which is asserted by an automated test that
reflects the schema and fails if a `tenant_id` table lacks `relforcerowsecurity` and a
policy.

### 5.6 Proving it

`tests/security/test_tenant_isolation_rls.py` runs as `buildseo_app` and asserts, for
each protected table, that with tenant A's context: a tenant-B row is invisible to
`SELECT`, `UPDATE … WHERE id = <B row>` affects 0 rows, `DELETE` affects 0 rows, an
`INSERT` carrying tenant B's id raises, and `SELECT … WHERE id = <B id>` (ID guessing)
returns nothing. A no-context test asserts zero rows everywhere.

---

## 6. Authentication Architecture

### 6.1 Tokens

| | Access | Refresh |
|---|---|---|
| Format | JWT (HS256, `JWT_SECRET`) | 256-bit opaque, URL-safe base64 |
| Lifetime | `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`, default 15 min | `JWT_REFRESH_TOKEN_EXPIRE_DAYS`, default 14 |
| Storage | client only | server stores **SHA-256 hash only** |
| Claims | `sub`, `jti`, `sid`, `tid?`, `typ=access`, `iat`, `nbf`, `exp`, `iss`, `aud` | n/a |

Refresh tokens are opaque, not JWTs: revocation must be authoritative, and an opaque
token that is worthless without its database row gives that for free.

### 6.2 Flows

```
POST /auth/register     create user (+ optional first tenant, seeded roles, owner membership)
POST /auth/login        email+password → verify Argon2id → session row → access+refresh
POST /auth/refresh      rotate: verify hash → revoke old → issue new pair (same family)
POST /auth/logout       revoke current session (or whole family)
POST /auth/select-tenant validate membership → new access token carrying tid
GET  /auth/sessions     list active sessions/devices
DELETE /auth/sessions/{id} revoke a session
```

### 6.3 Rotation and reuse detection

```
family_id groups every token descended from one login
refresh(token):
  h = sha256(token)
  row = SELECT … WHERE token_hash = h            -- constant-time by construction
  if row is None                → AuthenticationError
  if row.revoked                → revoke ENTIRE family, AuthenticationError  (replay!)
  if row.expires_at <= now()    → AuthenticationError
  revoke(row, reason="rotated"); insert new row in same family; return new pair
```

Reuse of an already-rotated token means the token leaked, so the whole family dies.
Sessions carry `user_agent`, `ip_address`, `last_used_at` for device management.

### 6.4 Tenant selection

The JWT never hard-binds a user to one tenant for life. `tid` is the *currently
selected* tenant and is re-validated against `tenant_memberships` on **every** request
— a stale or forged `tid` is worthless. `POST /auth/select-tenant` (or the
`X-Tenant-ID` header, equally validated) switches the active tenant.

### 6.5 Passwords

Argon2id (`argon2-cffi`), parameterized by config, with automatic re-hash on login
when parameters change. Strength policy: length ≥ 12, upper/lower/digit/symbol mix,
rejection of a common-password list and of email/name-derived passwords. Login returns
one indistinguishable error for unknown email and wrong password, and always performs
a hash verification against a dummy hash to avoid a user-enumeration timing oracle.

---

## 7. RBAC Architecture

```
user ──membership──▶ tenant
          │
          ├─ membership_roles ──▶ roles (per tenant)
                                   │
                                   └─ role_permissions ──▶ permissions (global catalog)
```

Authorization is **only ever** a permission check. There is no `if role == "admin"`
anywhere in the codebase; role names exist for humans.

```python
@router.post("/publishers", dependencies=[Depends(require_permission(Perm.PUBLISHER_CREATE))])
```

`require_permission` resolves the caller's effective permission set once per request
(single query joining membership → membership_roles → role_permissions → permissions),
caches it on the request principal, and raises `AuthorizationError` (403) on a miss.
`require_any_permission` / `require_all_permissions` cover compound cases.

### 7.1 Permission catalog

`tenant.{read,update}`, `user.{read,create,update,delete}`,
`role.{read,create,update,delete}`, `permission.read`,
`client_website.{read,create,update,delete}`, `campaign.{read,create,update,delete}`,
`publisher.{read,create,update,delete}`, `publisher.discover`, `publisher.qualify`,
`opportunity.{read,create,update,delete}`, `submission.{read,create,update,delete}`,
`submission.approve`, `submission.verify`, `credential.{read,create,update,delete}`,
`integration.{read,create,update,delete}`, `ai.generate`, `ai.usage.read`, `audit.read`,
`job.{read,create}`.

### 7.2 Default roles

| Role | Grant |
|---|---|
| **Owner** | every permission, including `tenant.update` and member/role administration |
| **Admin** | everything except ownership transfer and tenant deletion |
| **SEO Manager** | full campaign/publisher/opportunity/submission lifecycle incl. `submission.approve`, read-only on users/roles/credentials |
| **SEO Specialist** | read + create/update on opportunities and submissions, `ai.generate`; no approve, no delete, no credentials |
| **Viewer** | all `*.read` except `credential.read` and `audit.read` |

Seeded per tenant at creation, so a tenant may edit a copy of a role without affecting
anyone else. Custom roles are created through `POST /roles` with an explicit
permission list.

---

## 8. BYOK / Security Architecture

### 8.1 Envelope encryption

```
plaintext secret
   │  AES-256-GCM with a per-credential random DEK
   ▼
ciphertext + nonce ────────────────────────┐
                                            ├─▶ credentials row
DEK ─ AES-256-GCM with master KEK ─▶ encrypted_dek + dek_nonce + key_version
                                            ┘
master KEK ← ENCRYPTION_KEY (base64, 32 bytes) from env / secret manager
```

- A per-credential DEK means one compromised ciphertext does not compromise the rest,
  and re-keying rewraps DEKs without touching secret material.
- AAD binds each ciphertext to `tenant_id` + `credential_id` + `provider`, so a
  ciphertext moved between rows or tenants fails authentication.
- `KeyProvider` is a protocol; `EnvMasterKeyProvider` reads env today, an
  `AwsKmsKeyProvider`/`VaultKeyProvider` drops in later with no call-site changes.
  `key_version` is stored per row to support rotation.

### 8.2 Non-negotiables

- No provider key is ever in a response schema. `CredentialRead` exposes
  `provider`, `provider_type`, `label`, `status`, `masked_hint` (`sk-…abcd`),
  `last_verified_at`, timestamps — and nothing else. There is no "reveal" endpoint.
- Decryption happens only inside `CredentialService.resolve_secret()`, which returns a
  `SecretStr`-like wrapper consumed directly by a provider client.
- The logging redaction filter drops `authorization`, `password`, `token`,
  `refresh_token`, `api_key`, `secret`, `encryption_key`, `set-cookie` keys and any
  value matching known key prefixes, at the log-record level, so an accidental
  `logger.info(payload)` cannot leak.
- Audit metadata is built from allow-listed fields, never from raw request bodies.

### 8.3 Provider abstraction

```python
class AIProvider(Protocol):
    async def generate(self, request: GenerationRequest) -> GenerationResult: ...
    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult: ...

class PublisherDiscoveryProvider(Protocol):
    async def search(self, query: DiscoveryQuery) -> list[DiscoveredPublisher]: ...

class CrawlerProvider(Protocol):
    async def fetch_site(self, url: str) -> SiteSnapshot: ...

class SubmissionProvider(Protocol):
    async def submit(self, request: SubmissionRequest) -> SubmissionOutcome: ...
```

Business code depends on the protocol and on a *purpose*
(`AIProviderFactory.for_purpose(tenant, "content_generation")`). Swapping OpenAI for
Anthropic is a `tenant_ai_configs` row change. No vendor SDK is imported outside
`app/integrations/`; every implementation speaks HTTP through the shared client.

Every AI call writes an `ai_usage_records` row (provider, model, operation, tokens,
estimated cost, request id, status). Prompts are **not** stored; only the accepted
output is persisted, in `generated_contents`.

---

## 9. API Endpoint Inventory

All under `/api/v1`. Every response uses the `data`/`meta` envelope; every error uses
the `error` envelope. `A` = requires access token, `T` = requires active tenant.

| Method | Path | Auth | Permission |
|---|---|---|---|
| GET | `/health`, `/health/live`, `/health/ready` | – | – |
| POST | `/auth/register` | – | – |
| POST | `/auth/login` | – | – |
| POST | `/auth/refresh` | – | – |
| POST | `/auth/logout` | A | – |
| POST | `/auth/select-tenant` | A | – |
| GET | `/auth/sessions` | A | – |
| DELETE | `/auth/sessions/{id}` | A | – |
| GET | `/me` | A | – |
| PATCH | `/me` | A | – |
| POST | `/me/password` | A | – |
| GET | `/me/tenants` | A | – |
| GET | `/tenants` | A | – |
| POST | `/tenants` | A | – |
| GET | `/tenants/{tenant_id}` | A+T | `tenant.read` |
| PATCH | `/tenants/{tenant_id}` | A+T | `tenant.update` |
| GET | `/tenants/{tenant_id}/members` | A+T | `user.read` |
| POST | `/tenants/{tenant_id}/members` | A+T | `user.create` |
| PATCH | `/tenants/{tenant_id}/members/{id}` | A+T | `user.update` |
| DELETE | `/tenants/{tenant_id}/members/{id}` | A+T | `user.delete` |
| GET | `/users` | A+T | `user.read` |
| GET | `/users/{id}` | A+T | `user.read` |
| GET | `/roles` | A+T | `role.read` |
| POST | `/roles` | A+T | `role.create` |
| GET | `/roles/{id}` | A+T | `role.read` |
| PATCH | `/roles/{id}` | A+T | `role.update` |
| DELETE | `/roles/{id}` | A+T | `role.delete` |
| GET | `/permissions` | A+T | `permission.read` |
| GET/POST | `/client-websites` | A+T | `client_website.read` / `.create` |
| GET/PATCH/DELETE | `/client-websites/{id}` | A+T | `client_website.*` |
| GET/POST | `/campaigns` | A+T | `campaign.read` / `.create` |
| GET/PATCH/DELETE | `/campaigns/{id}` | A+T | `campaign.*` |
| GET/POST | `/publishers` | A+T | `publisher.read` / `.create` |
| GET/PATCH/DELETE | `/publishers/{id}` | A+T | `publisher.*` |
| POST | `/publishers/discover` | A+T | `publisher.discover` |
| POST | `/publishers/{id}/qualify` | A+T | `publisher.qualify` |
| GET | `/publishers/discovery-runs` | A+T | `publisher.read` |
| GET/POST | `/opportunities` | A+T | `opportunity.read` / `.create` |
| GET/PATCH | `/opportunities/{id}` | A+T | `opportunity.*` |
| POST | `/opportunities/{id}/qualify` | A+T | `opportunity.update` |
| POST | `/opportunities/{id}/select` | A+T | `opportunity.update` |
| POST | `/opportunities/{id}/reject` | A+T | `opportunity.update` |
| POST | `/opportunities/{id}/generate-content` | A+T | `ai.generate` |
| GET | `/opportunities/{id}/content` | A+T | `opportunity.read` |
| POST | `/opportunities/{id}/content/{cid}/review` | A+T | `opportunity.update` |
| GET/POST | `/submissions` | A+T | `submission.read` / `.create` |
| GET/PATCH | `/submissions/{id}` | A+T | `submission.*` |
| POST | `/submissions/{id}/approve` | A+T | `submission.approve` |
| POST | `/submissions/{id}/execute` | A+T | `submission.update` |
| POST | `/submissions/{id}/verify` | A+T | `submission.verify` |
| POST | `/submissions/{id}/transition` | A+T | `submission.update` |
| GET/POST | `/credentials` | A+T | `credential.read` / `.create` |
| GET/PATCH/DELETE | `/credentials/{id}` | A+T | `credential.*` |
| GET/PUT | `/ai/configs` | A+T | `integration.read` / `.update` |
| GET | `/ai/usage` | A+T | `ai.usage.read` |
| GET | `/audit-logs` | A+T | `audit.read` |
| GET | `/jobs` | A+T | `job.read` |

Collections accept `page`, `page_size`, `sort`, `order`, `q` (search) and
resource-specific filters (`status`, `pricing_type`, `campaign_id`, `country`, …).

---

## 10. Submission State Machine

Opportunity lifecycle:

```mermaid
stateDiagram-v2
    [*] --> DISCOVERED
    DISCOVERED --> QUALIFYING
    QUALIFYING --> QUALIFIED
    QUALIFYING --> REJECTED
    QUALIFIED --> SELECTED
    QUALIFIED --> REJECTED
    SELECTED --> READY
    SELECTED --> REJECTED
    READY --> SUBMITTED
    READY --> REJECTED
    SUBMITTED --> PUBLISHED
    SUBMITTED --> FAILED
    FAILED --> READY
    QUALIFIED --> EXPIRED
    READY --> EXPIRED
    PUBLISHED --> [*]
```

Submission lifecycle — the human-in-the-loop gate is `PENDING_APPROVAL → SUBMITTED`:

```mermaid
stateDiagram-v2
    [*] --> READY
    READY --> IN_PROGRESS : prepare (AI drafts content)
    IN_PROGRESS --> PENDING_APPROVAL : content ready for review
    PENDING_APPROVAL --> IN_PROGRESS : changes requested
    PENDING_APPROVAL --> SUBMITTED : human approves + execute
    PENDING_APPROVAL --> REJECTED : human rejects
    SUBMITTED --> VERIFICATION_PENDING : awaiting publication
    SUBMITTED --> PUBLISHED : publisher confirmed
    SUBMITTED --> FAILED
    VERIFICATION_PENDING --> PUBLISHED
    VERIFICATION_PENDING --> FAILED
    PUBLISHED --> VERIFIED : link found on live page
    PUBLISHED --> FAILED : link missing/removed
    FAILED --> READY : retry
    REJECTED --> [*]
    VERIFIED --> [*]
```

Rules enforced by `SubmissionWorkflow` (a declarative transition table, not scattered
`if`s):

1. Transitions not in the table raise `SubmissionError` (409).
2. A submission cannot exist for an opportunity whose publisher is not
   `pricing_type = FREE` — checked in the service **and** guarded by a DB trigger on
   the submission path.
3. `SUBMITTED` requires an approval record (`approved_by_user_id`, `approved_at`) set
   by a caller holding `submission.approve`.
4. Automated form submission is opt-in per publisher (`submission_method = FORM`) and
   the `FormSubmissionProvider` **refuses** any target that presents a CAPTCHA,
   an anti-bot challenge, or a `robots.txt`/ToS restriction — it returns
   `BLOCKED_REQUIRES_MANUAL` and the workflow falls back to `ManualSubmission`.
   No CAPTCHA solving, no anti-bot evasion, ever.
5. Verification is an abstraction (`LinkVerifier`) that fetches the submitted URL and
   looks for the target link; it never mutates publisher state directly.

---

## 11. Migration Plan

Alembic only; one concern per revision, each with a working `downgrade`.

| # | Revision | Contents |
|---|---|---|
| 001 | `initial_extensions` | `pgcrypto`, `citext`, `app_current_tenant_id()`, `app_current_user_id()`, `set_updated_at()` trigger fn |
| 002 | `users` | users table + indexes |
| 003 | `tenants` | tenants table |
| 004 | `memberships` | tenant_memberships |
| 005 | `permissions` | global permission catalog |
| 006 | `roles` | per-tenant roles |
| 007 | `rbac_links` | role_permissions, membership_roles |
| 008 | `refresh_sessions` | session/token-family store |
| 009 | `client_websites` | client websites |
| 010 | `campaigns` | campaigns (+ `free_only` MVP check) |
| 011 | `publishers` | publishers, discovery_runs |
| 012 | `opportunities` | opportunities |
| 013 | `submissions` | submissions, generated_contents (+ FREE-only trigger) |
| 014 | `credentials` | credentials, tenant_ai_configs |
| 015 | `ai_usage` | ai_usage_records |
| 016 | `audit_jobs_idempotency` | audit_logs, jobs, idempotency_keys |
| 017 | `rls_policies` | ENABLE + FORCE RLS and policies on every tenant-owned table |
| 018 | `indexes_and_grants` | composite/partial indexes, grants to the app role |

Rules: no manual production DDL; every tenant-owned table gets its RLS in 017 so the
policy set is reviewable in one place; grants are applied to a configurable role name
(`DB_APP_ROLE`) and skipped if the role is absent, so the same migration runs in CI,
dev and production.

---

## 12. Testing Strategy

| Suite | Scope | How |
|---|---|---|
| `tests/unit` | password hashing & policy, JWT encode/decode/expiry, refresh rotation logic, envelope encryption/decryption + AAD tamper, domain normalization, scoring, qualification rules, submission state machine, pagination | pure functions, no DB |
| `tests/integration` | repositories, transactions, unique constraints, idempotency, task queue claim semantics, seed correctness | real PostgreSQL, per-test transaction rollback |
| `tests/security` | **RLS**: cross-tenant read/update/delete/insert/ID-guess per table, no-context default-deny, schema audit that every `tenant_id` table is protected; RBAC denial; expired/revoked/invalid tokens; credential non-leakage | runs as `buildseo_app` (NOBYPASSRLS) |
| `tests/api` | auth flows, tenant switching, CRUD, validation errors, pagination/filtering/sorting, error envelope shape, OpenAPI completeness | `httpx.AsyncClient` + `ASGITransport` |

Test database: created once, migrated with Alembic (proving migrations run from clean),
then each test runs in a transaction that is rolled back. RLS tests use a second
engine bound to the `NOBYPASSRLS` role. Fixtures build two full tenants (A and B) with
distinct users, roles and domain rows, so cross-tenant assertions are always available.

Acceptance gate: `ruff`, `black --check`, `mypy` on `app/core`, `app/auth`, `app/rbac`,
and the full `pytest` suite green against a database built purely from migrations.
