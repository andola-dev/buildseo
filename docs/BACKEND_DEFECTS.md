# Backend defects found while integrating the frontend

Hand this file to whoever works on
`claude/saas-link-discovery-backend-768jmc`. Every item below was reproduced
against a live instance, not inferred from reading code.

**Nothing here has been fixed.** The backend branch is untouched — local
patches used to confirm the diagnoses were reverted.

## How this was reproduced

```bash
# Postgres 16, roles per docker/postgres/init/00-create-app-role.sh
#   buildseo       LOGIN SUPERUSER               (migrations)
#   buildseo_app   NOSUPERUSER NOBYPASSRLS       (runtime)
cd backend
alembic upgrade head                                   # all 18 migrations OK
SEED_OWNER_PASSWORD='…' python -m scripts.seed \
  --owner-email owner@example.com --workspace "Acme Marketing"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Database state afterwards is correct — this is not a seeding problem:

```
tenants:             1 row  (Acme Marketing, ACTIVE)
tenant_memberships:  1 row  (ACTIVE, is_owner = t)
users:               1 row  (owner@example.com)
```

## Summary

| ID | Severity | Area | One-line |
| --- | --- | --- | --- |
| BE-1 | **Blocking** | RLS / tenant resolution | No tenant-scoped endpoint can succeed for any user |
| BE-2 | **Blocking** | Auth | `POST /auth/select-tenant` returns 403 for a valid membership |
| BE-3 | High | Auth | `POST /auth/login` silently ignores a `tenant_id` it cannot validate |
| BE-4 | High | Tenants | `POST /tenants` succeeds but the new workspace is undiscoverable |
| BE-5 | Medium | API design | `/me` and every other endpoint disagree on how the active tenant is determined |
| BE-6 | Low | Config | `CORS_ORIGINS` rejects the JSON-array form; format is undocumented |
| BE-7 | Low | Tooling | `scripts/seed.py` documents an `--owner-password` flag that does not exist |

BE-2, BE-3 and BE-4 are all consequences of BE-1's root cause, but each is a
separate call site and each needs its own regression test.

---

## BE-1 — Blocking: RLS deadlock makes every tenant-scoped endpoint 403

### Symptom

After a successful login, every workspace-scoped request fails:

```
GET /api/v1/campaigns         403 TENANT_ACCESS_DENIED
GET /api/v1/client-websites   403 TENANT_ACCESS_DENIED
GET /api/v1/publishers        403 TENANT_ACCESS_DENIED
GET /api/v1/opportunities     403 TENANT_ACCESS_DENIED
GET /api/v1/submissions       403 TENANT_ACCESS_DENIED
GET /api/v1/credentials       403 TENANT_ACCESS_DENIED
GET /api/v1/roles             403 TENANT_ACCESS_DENIED
GET /api/v1/permissions       403 TENANT_ACCESS_DENIED
GET /api/v1/audit-logs        403 TENANT_ACCESS_DENIED
```

…with a valid bearer token **and** a correct `X-Tenant-ID` header, for a user
whose membership row is `ACTIVE` and `is_owner`. Related reads come back empty
rather than erroring:

```jsonc
GET /api/v1/me         → { "tenants": [], "permissions": [], "active_tenant_id": null }
GET /api/v1/me/tenants → { "data": [], "meta": { "total": 0 } }
GET /api/v1/tenants    → { "data": [], "meta": { "total": 0 } }   // HTTP 200
```

The result is a hard bootstrap deadlock: a user cannot select a workspace
because they cannot list their workspaces, and cannot list them because no
workspace is selected.

### Root cause

`migrations/versions/0017_rls_policies.py` enables RLS on
`tenant_memberships` with two policies:

```sql
tenant_memberships_tenant_isolation  USING (tenant_id = app_current_tenant_id())
tenant_memberships_self_read         USING (user_id  = app_current_user_id())
```

`app/api/dependencies/tenant.py::get_tenant_context` then reads
`tenant_memberships` **before** any context is established, on a session from
`get_unscoped_session` where both `app.current_tenant_id` and
`app.current_user_id` are NULL. Both policies evaluate false, the row is
invisible, `membership is None`, and the dependency raises
`TenantAccessError` — the uniform refusal intended for a genuine
non-member.

`tenant_memberships_self_read` exists for precisely this bootstrap case. It is
simply never activated, because nothing sets `app.current_user_id` before the
lookup.

### Evidence (database level)

```
-- as buildseo_app, no context set
select count(*) from tenant_memberships;                        -- 0

-- as buildseo_app, user bound
set app.current_user_id = '01a08013-552c-…';
select count(*) from tenant_memberships;                        -- 1
```

So the row is present and the policy works; only the binding is missing.

### Affected call sites

Found by fixing them one at a time — each hid the next:

| # | Location | Broken behaviour |
| --- | --- | --- |
| 1 | `app/api/dependencies/tenant.py::get_tenant_context` | all tenant-scoped endpoints 403 |
| 2 | `app/api/v1/me.py::read_me`, `list_my_tenants` | workspace list empty, so nothing is selectable |
| 3 | `app/auth/service.py::_require_membership` | see BE-2 |

`_require_membership` is described in its own docstring as "the single choke
point for tenant authorisation … every path that scopes a token or a request to
a workspace goes through here", which is why the same omission surfaces in
several unrelated places.

### Suggested fix

`TenantAwareSession.set_tenant_context` already accepts `tenant_id=None`, so
the missing step is binding the authenticated principal before the membership
read:

```python
await session.set_tenant_context(tenant_id=None, user_id=principal.user_id)
```

Because the same omission recurs at every site, prefer fixing it **once at the
session layer** — bind the principal in `get_unscoped_session` (which needs
access to the principal, or a `set_user_id` contextvar read; note
`app/core/context.py` already has a `user_id` ContextVar that
`app/api/dependencies/auth.py:101` sets via `set_user_id(user.id)`) — rather
than patching each caller and waiting for the next one to be found.

### Implementation caution (learned the hard way)

A naive per-site patch that calls `set_tenant_context(tenant_id=None, …)`
**resets an already-established tenant context**. Adding it inside
`_require_membership` made `GET /me` start returning
`400 TENANT_CONTEXT_REQUIRED`, because a later tenant-scoped read in the same
request then hit `require_tenant_id()` with `_tenant_id` back to `None`.

Whatever the fix, it must bind the *user* without clearing a tenant that is
already set. A dedicated `set_user_context(user_id)` that leaves `_tenant_id`
alone would be safer than reusing `set_tenant_context`.

### Verification

Applying the binding at site 1 turned all nine 403s into 200s. Adding it at
site 2 made `GET /me` return both workspaces
(`['Acme Marketing', 'Second Workspace']`). Both were confirmed before the
patches were reverted.

---

## BE-2 — Blocking: `POST /auth/select-tenant` rejects a valid membership

### Symptom

```
POST /api/v1/auth/select-tenant
Authorization: Bearer <valid token>
{"tenant_id": "01a08013-5534-7399-84ec-b331394528dc"}

403 {"error":{"code":"TENANT_ACCESS_DENIED",
              "message":"You do not have access to this tenant"}}
```

The tenant id is that of a workspace the caller owns.

### Root cause

`app/auth/service.py::select_tenant` → `_require_membership`, which performs
the same unscoped membership read described in BE-1.

### Why it matters independently

This is the documented way to choose a workspace, and it is the only path that
mints a `tid`-bearing access token. With it broken, even a client that already
knows the workspace id cannot obtain a scoped session, so BE-1 cannot be worked
around from the client side.

### Fix

Covered by the BE-1 session-layer fix. Worth its own test.

---

## BE-3 — High: login silently ignores an unvalidatable `tenant_id`

### Symptom

```
POST /api/v1/auth/login
{"email":"owner@example.com","password":"…",
 "tenant_id":"01a08013-5534-7399-84ec-b331394528dc"}

200 { "data": { "access_token": "…", "active_tenant_id": null } }
```

A valid, owned `tenant_id` was supplied; the response is `200` with
`active_tenant_id: null`. The log line reads
`"login succeeded without a workspace"`.

### Why it matters

`LoginRequest.tenant_id` is documented as "Membership is validated
server-side; an unauthorised value is rejected." It is not rejected — it is
dropped. A client that asks for a workspace and gets `200` reasonably assumes
it got one.

The silent downgrade is also what made BE-1 hard to attribute: login looks
successful, and the failure only appears later as unrelated 403s.

### Suggested fix

Decide explicitly and document it: either reject an unusable `tenant_id`
(`403 TENANT_ACCESS_DENIED`, matching the schema description), or keep the
downgrade but make it observable to the caller. Silently returning `200` with
a different active tenant than requested is the one option that should go.

Note that once BE-1 is fixed the validation itself will start succeeding, so
this is about the *failure* contract, not the happy path.

---

## BE-4 — High: a newly created workspace is undiscoverable

### Symptom

```
POST /api/v1/tenants  {"name":"Second Workspace"}     201 Created
GET  /api/v1/me/tenants                              { "data": [], "total": 0 }
```

Creation succeeds and returns the new tenant, but it never appears in the
caller's workspace list, so it can never be selected. For a user with no
workspace this is a dead end: the only self-service escape hatch does not work.

### Root cause

The membership row created alongside the tenant is invisible to the subsequent
listing read (BE-1).

### Note

`POST /auth/register` with `tenant_name` **does** yield a working
`active_tenant_id`, because it mints the token directly rather than reading the
membership back. That asymmetry is a useful signal for confirming the fix:
register and create-workspace should behave the same afterwards.

---

## BE-5 — Medium: `/me` and everything else disagree on the active tenant

### Observation

`app/api/dependencies/tenant.py` documents the header as authoritative:

> The workspace can be named by the token's `tid` claim or by an
> `X-Tenant-ID` header … Both are treated identically.

But `app/api/v1/me.py::read_me` reads only `principal.claimed_tenant_id` — the
token claim — for both `active_tenant_id` and `permissions`:

```python
permissions: list[str] = []
if principal.claimed_tenant_id is not None:
    permissions = sorted(await auth.effective_permissions(...))
```

So `GET /me` with `X-Tenant-ID: <workspace>` reports
`active_tenant_id: null, permissions: []`, while every other endpoint in the
same request pattern honours the header. Role names are also only populated
for `principal.claimed_tenant_id`.

### Why it matters

A client that follows the header contract gets an empty permission set from
`/me` and — with permission-gated navigation — renders an application with
every feature hidden, while its data requests succeed. The two halves of the
API disagree.

### Suggested fix

Pick one and make it consistent: either have `read_me` resolve the active
tenant the same way as `get_tenant_context` (header overrides claim), or
narrow the dependency's docstring and document that `/me` is
token-claim-scoped only.

### Current frontend behaviour

The frontend assumes **token-claim** semantics, since that is what the code
does: `AuthProvider` calls `POST /auth/select-tenant` during bootstrap to mint
a scoped token before relying on `/me` permissions. If this is changed to
header semantics, that call becomes redundant but harmless.

---

## BE-6 — Low: `CORS_ORIGINS` rejects the JSON-array form

### Symptom

```
CORS_ORIGINS=["http://localhost:3000"]

pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
cors_origins
  Input should be a valid list [type=list_type,
    input_value='["http://localhost:3000"]', input_type=str]
```

The application refuses to start. `CORS_ORIGINS=http://localhost:3000`
(comma-separated) works.

### Why it matters

`pydantic-settings` normally parses JSON for complex types, so the JSON form is
the natural first guess, and `.env.example` documents neither form. It costs
whoever sets the project up a debugging cycle before anything runs.

### Suggested fix

Document the expected format in `.env.example`, and/or accept both by parsing
JSON when the value looks like a JSON array.

---

## BE-7 — Low: `scripts/seed.py` documents a flag it does not implement

### Symptom

The module docstring advertises:

> The optional ``--owner-email``/``--owner-password`` …

but `_parse_args` defines only `--owner-email` and `--workspace`. Passing
`--owner-password` is an argparse error; the password actually comes from
`SEED_OWNER_PASSWORD`, which only the runtime error message reveals:

```
No password available: set SEED_OWNER_PASSWORD or run this interactively.
```

### Suggested fix

Correct the docstring to name the environment variable (deliberately not a
flag, so the password stays out of shell history — worth saying explicitly),
or mention `SEED_OWNER_PASSWORD` in the `--owner-email` help text.

---

## Suggested regression tests

The deadlock is invisible to any test that sets up context by hand, which is
probably why it was not caught. Each of these should fail today:

1. **Bootstrap, end to end.** Seed a user with one workspace, `POST
   /auth/login` **without** `tenant_id`, then assert
   `GET /me` lists the workspace, `POST /auth/select-tenant` returns 200, and
   a tenant-scoped `GET` (e.g. `/campaigns`) returns 200. This single test
   covers BE-1, BE-2 and BE-4.
2. **Header parity.** `GET /me` with `X-Tenant-ID` and a claimless token
   returns the same `permissions` as with a scoped token (BE-5) — or assert the
   documented alternative, once decided.
3. **Login with an unusable `tenant_id`** asserts the chosen contract rather
   than a silent `200` + `null` (BE-3).
4. **Create-then-select.** `POST /tenants` followed by
   `GET /me/tenants` lists the new workspace (BE-4).
5. **Runtime role, no context.** A direct assertion that
   `tenant_memberships` self-read works for a bound user and returns nothing
   for an unbound one — pinning the RLS behaviour the fix depends on.

Tests should run as the `NOSUPERUSER NOBYPASSRLS` runtime role. A test suite
connecting as the migration superuser would bypass RLS entirely and pass
regardless.

## What the frontend already does about this

No workarounds and no mock data — the gaps are surfaced honestly instead:

- `AuthProvider` mints a scoped token via `/auth/select-tenant` at bootstrap
  (BE-5 semantics), with at-most-once retry per workspace so a 403 cannot
  become a request loop.
- A user with no resolvable workspace gets an explicit "No workspace yet"
  screen rather than a wall of 403s.
- The Playwright `signIn` helper fails with a message naming BE-1, so the
  workflow specs failing today is not mistaken for a frontend regression.
- `docs/API_CONTRACT.md` records these alongside the seven endpoints the
  frontend needs that the backend does not expose.
