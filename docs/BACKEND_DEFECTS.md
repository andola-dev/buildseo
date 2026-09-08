# Backend defects found while integrating the frontend

Hand this file to whoever works on
`claude/saas-link-discovery-backend-768jmc`. Every item below was reproduced
against a live instance, not inferred from reading code.

> **Status: BE-1 .. BE-7 resolved** (verified against `main` at `8f9bfcd`; see
> the "Resolution" section for what changed). Kept in the repository because
> the reproduction steps and the root-cause analysis remain the best
> description of *why* the code is shaped the way it now is.
>
> **BE-8 is open** and was found only after those fixes landed — the RLS
> deadlock they cured was masking it. It is filed at the end of this file,
> under "Round two". It currently blocks the end-to-end suite.

Originally filed with nothing fixed and the backend branch untouched — the
local patches used to confirm the diagnoses were reverted.

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
| **BE-8** | **Blocking** | RBAC / RLS | **OPEN.** `/me` returns `permissions: []` and `roles: []` for a workspace owner |

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

---

## Resolution

Fixed on top of the merged backend, in one change per root cause rather than
one per symptom.

### The root cause, and why it hid

`tenant_memberships` is RLS-protected and `tenant_memberships_self_read` keys
on `app_current_user_id()`. Nothing bound the principal before a membership
read, so the policy never activated. This report's diagnosis was correct in
every particular, including the warning that a naive
`set_tenant_context(tenant_id=None, …)` patch would clear an established tenant
and turn the fix into a `400 TENANT_CONTEXT_REQUIRED` elsewhere.

`TenantAwareSession.set_user_context(user_id)` binds the user and leaves
`_tenant_id` alone, so it is safe to call at any point in a request. It is
called in exactly two places, which between them cover every path:

- `get_principal` — once per request, before `get_tenant_context` runs. FastAPI
  caches the session per request, so this scopes every later read on it. It
  cannot live in `get_unscoped_session`, which has no principal yet: the token
  must be validated first, and the tables that do so (`users`,
  `refresh_sessions`) are global and readable unbound.
- `AuthService._require_membership` — the authorisation choke point, reached by
  login and refresh without any principal dependency having run.

### A fourth call site this report did not reach

`AuthService.refresh` re-validates the remembered workspace against membership,
"so a token cannot outlive the access it represents". Unbound, that read saw no
membership **ever**, so every refresh silently de-scoped a perfectly good
session — indistinguishable from a genuine revocation, and invisible in the
logs beyond a line saying the scope was dropped. Now bound before the check.

### Why the test suite did not catch any of it

`tests/fixtures/database.py::resources` built the application container on the
**owner** engine. That role is a SUPERUSER, which bypasses RLS entirely, so all
112 API tests exercised every endpoint with Row-Level Security effectively
switched off — green while the running application was unusable. It now uses
`rls_engine`; fixtures still *seed* through the owner engine, because setting up
two tenants' data is not what is under test.

This is the class of failure the CI workflow's "runtime role cannot bypass RLS"
step was meant to prevent. That step checks the *role*; it could not check that
the API suite actually *used* it.

### Item by item

| ID | Resolution |
| --- | --- |
| BE-1 | `set_user_context`, called at the two sites above. |
| BE-2 | Same fix — `select_tenant` goes through `_require_membership`. Covered by `test_a_member_can_reach_their_workspace_from_a_plain_login`. |
| BE-3 | Already correct once BE-1 is fixed: `_resolve_login_tenant` routes an explicit `tenant_id` through `_require_membership`, which raises `TenantAccessError`. The observed `200` + `null` was BE-1 downstream, not a separate silent-drop path. Pinned by `test_an_unowned_workspace_is_rejected_not_silently_dropped` rather than changed speculatively. |
| BE-4 | Same fix. Covered by `test_a_new_workspace_is_immediately_discoverable`, which also asserts the seeded roles arrive with it. |
| BE-5 | Resolved in favour of the documented contract: the header wins, falling back to the token claim. `get_requested_tenant_id` is now the single shared rule, used by both `get_tenant_context` and `read_me`, so the two halves cannot drift apart again. `/me` validates the resolved workspace against the caller's own memberships and reports `null` rather than 403 — it is the discovery endpoint, so it must answer even when asked for a workspace the caller cannot enter. The frontend's `select-tenant` bootstrap becomes redundant but stays harmless. |
| BE-6 | The validator recognised the JSON form and then returned the string unparsed, which failed as "Input should be a valid list" because the field is `NoDecode`. It now parses it, raises a clear error for malformed JSON or a JSON object, and both forms are documented in `.env.example`. |
| BE-7 | Docstring corrected, and `--owner-email`'s help text now names `SEED_OWNER_PASSWORD` and says why it is deliberately not a flag. |

### Regression tests

All five the report suggested, plus the refresh case:

- `tests/api/test_bootstrap.py` — the end-to-end bootstrap, workspace listing
  and its isolation, permissions for the active workspace, create-then-select,
  header/claim parity, the graceful-degradation case, the login contract, and
  refresh keeping its scope.
- `tests/security/test_tenant_isolation_rls.py::TestMembershipSelfRead` — the
  policy itself: unbound sees nothing, a bound user sees only their own rows,
  the policy is SELECT-only, and `set_user_context` does not clear an
  established tenant.

---

# Round two — filed after the BE-1..BE-7 fixes landed

Reproduced against `main` at `8f9bfcd` ("fix: bind the principal before every
membership read, and test under RLS"), with the same live instance and the same
NOSUPERUSER NOBYPASSRLS runtime role as above. This defect was not visible
before, because BE-1 stopped `/me` from resolving an active workspace at all —
an empty permission set looked like a symptom of BE-1 rather than a second bug
sitting behind it.

## BE-8 — Blocking: `/me` reports no permissions and no roles, even for an owner

### Symptom

A workspace owner with all 50 permissions gets an empty permission set from the
one endpoint the client uses to discover what it may do:

```bash
# 1. plain login (this account belongs to two workspaces, so no tid claim)
AT=$(curl -s -X POST localhost:8000/api/v1/auth/login \
      -H 'Content-Type: application/json' \
      -d '{"email":"owner@example.com","password":"…"}' | jq -r .data.access_token)

# 2. select a workspace — succeeds, and mints a workspace-scoped token
AT2=$(curl -s -X POST localhost:8000/api/v1/auth/select-tenant \
      -H "Authorization: Bearer $AT" -H 'Content-Type: application/json' \
      -d '{"tenant_id":"01a0808f-…-205c6db0ea10"}' | jq -r .data.access_token)

# 3. GET /me with that scoped token
curl -s localhost:8000/api/v1/me -H "Authorization: Bearer $AT2"
```

```json
{
  "active_tenant_id": "01a0808f-f345-701f-9ede-205c6db0ea10",   ← resolves correctly
  "tenants": [
    { "tenant_name": "Acme Marketing", "is_owner": true, "roles": [] },   ← empty
    { "tenant_name": "Growth Agency",  "is_owner": true, "roles": [] }    ← empty
  ],
  "permissions": []                                                      ← empty
}
```

The workspace *identity* half of the response is right — `active_tenant_id`,
`tenant_name`, `tenant_slug`, `status` and `is_owner` are all correct, so this
is clearly not BE-1 recurring. Only the two RBAC fields are empty.

`GET /api/v1/roles` for the same account and the same workspace is correct,
which is what makes the diagnosis unambiguous:

```
[('viewer', 9), ('seo_specialist', 18), ('seo_manager', 34), ('owner', 50), ('admin', 48)]
```

So the rows exist, the grants exist, and a tenant-scoped endpoint can read
them. Only `/me` cannot.

### Root cause

`read_me` runs on `UnscopedServicesDep`. By design (see the docstring on
`TenantAwareSession.set_user_context`) that session has **only**
`app.current_user_id` bound — `set_user_context` deliberately leaves the tenant
alone so it can be called at any point in a request without clearing an
established context. That is the right call for BE-1's fix, and it is exactly
what breaks here.

`membership_roles` and `role_permissions` are both in
`migrations/versions/0017_rls_policies.py::TENANT_OWNED_TABLES`, and their only
policy is:

```sql
CREATE POLICY <table>_tenant_isolation ON <table>
    FOR ALL USING (tenant_id = app_current_tenant_id())
```

With no tenant bound, `app_current_tenant_id()` is NULL, the predicate is never
true, and both tables read as empty. Unlike `tenant_memberships`, neither has a
user-keyed escape hatch equivalent to `tenant_memberships_self_read`.

Both of `/me`'s RBAC lookups go through those tables:

| Location | Reads | Result unbound |
| --- | --- | --- |
| `app/api/v1/me.py::read_me` → `services.membership_roles.list_roles_for_membership` | `membership_roles` → `roles` | `roles: []` |
| `app/api/v1/me.py::read_me` → `auth.effective_permissions` → `EffectivePermissionRepository.codes_for_user_in_tenant` | `permissions ⋈ role_permissions ⋈ membership_roles ⋈ tenant_memberships` | `permissions: []` |

Note that `codes_for_user_in_tenant` already constrains `MembershipRole.tenant_id`
and `RolePermission.tenant_id` in SQL, so the query is correctly scoped on its
own merits. RLS is filtering rows the query had already narrowed itself — the
tenant predicate is redundant here, not protective.

### Evidence (database level)

As `buildseo_app` (NOSUPERUSER NOBYPASSRLS), binding exactly what `GET /me`
binds — the user and nothing else:

```sql
BEGIN;
SET LOCAL app.current_user_id = '01a08085-…-e876040d4b02';
-- deliberately NO app.current_tenant_id, exactly as GET /me runs
```

```
role: buildseo_app bypassrls=false
memberships visible:                                2     ← self_read policy works
membership_roles visible:                           0     ← tenant predicate, NULL tenant
role_permissions visible:                           0     ← same
permissions (global) visible:                      50     ← not tenant-owned
effective-permission join:                          0     ← the /me result
```

Then, in the same transaction, adding the tenant the request had already
resolved:

```sql
SET LOCAL app.current_tenant_id = '01a0808f-…-205c6db0ea10';
```

```
with tenant bound, effective-permission join:      50     ← correct
```

Nothing about the data or the query changed between those two counts. The only
variable is whether a tenant is bound.

### Why it matters

`/me.permissions` is the *only* source the client has for what the user may do.
`GET /roles` describes the workspace's roles, not the caller's grants, and the
access token deliberately carries no permission claims (the endpoint's own
description says permissions are "resolved from the database on every call
rather than read from the token, so a role change is reflected immediately").

An owner therefore lands in a workspace where the frontend can prove no
capability at all:

- permission-gated navigation renders **only "Dashboard"** — every other
  section is filtered out by `src/config/navigation.ts`
- every `<PermissionGate>` action is withheld, so screens reachable by URL
  render read-only with no primary action

That last point is what fails the E2E suite. `e2e/link-building-workflow.spec.ts`
reaches `/campaigns`, sees the page render correctly, and then times out
waiting for the `New campaign` link, which sits behind
`<PermissionGate permission={PERM.CAMPAIGN_CREATE}>`:

```
✘ create a campaign through the guided wizard (1.0m)
  waiting for getByRole('link', { name: /new campaign/i })
```

Five dependent specs then do not run. The frontend is behaving correctly: it is
refusing to offer actions the backend says the user does not have. Per §32 the
frontend must not second-guess a server permission answer, so this cannot be
worked around client-side, and it should not be.

### Suggested fix

The request has already validated the workspace by the time `/me` needs these
rows — `active_tenant_id` is resolved and membership-checked a few lines
earlier. So bind it for the RBAC reads and let RLS agree with the query that is
already scoped:

```python
# app/api/v1/me.py::read_me, after active_tenant_id is resolved
if active_tenant_id is not None:
    await session.set_tenant_context(
        tenant_id=active_tenant_id, user_id=principal.user_id
    )
```

This is a *validated* tenant, not a claimed one — the `next(...)` above only
yields a `tenant_id` that appears in this user's own ACTIVE memberships — so it
grants nothing the caller was not already entitled to.

Three notes on doing it this way:

1. **Do not** reach for a new user-keyed RLS policy on `membership_roles` /
   `role_permissions`. `tenant_memberships_self_read` is justified because that
   table must be readable *before* any tenant is known; here the tenant is
   known, so widening the policy set would trade a precise fix for a permanent
   hole in the isolation model.
2. **Do not** use `set_user_context` — it preserves `_tenant_id` precisely so
   it cannot establish one, which is the whole reason BE-1's fix was safe.
3. Ordering matters: `roles_by_membership` and `effective_permissions` must
   both run *after* the bind. The roles comprehension currently sits above the
   permission lookup and would otherwise still see zero rows.

An alternative, if binding inside `/me` is unwelcome: have `read_me` depend on
the optional-tenant variant of `get_tenant_context` (validate-and-bind, but
report `null` instead of raising when the workspace is absent or unenterable),
so the "discovery endpoint must still answer" property BE-5 established is
preserved while the session ends up bound the same way every other endpoint
binds it. That is the tidier shape if more unscoped endpoints ever need
tenant-owned reads.

### Verification

```bash
# scoped token, as in the reproduction above
curl -s localhost:8000/api/v1/me -H "Authorization: Bearer $AT2" \
  | jq '{active: .data.active_tenant_id, perms: (.data.permissions|length),
         roles: [.data.tenants[].roles]}'
```

Expected for the seeded owner:

```json
{ "active": "01a0808f-…", "perms": 50, "roles": [[], ["owner"]] }
```

`roles` is empty for the *non*-active workspace by design — `read_me` only
builds `roles_by_membership` for `active_tenant_id`, with the comment "Role
names are tenant-owned, so they can only be read for the workspace this request
is scoped to". That stays true after the fix and is the correct behaviour.

### Suggested regression tests

1. `tests/api/test_bootstrap.py` — after login and select-tenant, `/me` returns
   a non-empty `permissions` for a seeded owner, and `roles` containing
   `"owner"` for the active workspace. This is the assertion that would have
   caught it: the existing bootstrap tests assert `active_tenant_id` resolves,
   but not that the RBAC fields are populated.
2. The same, driven by the `X-Tenant-ID` header rather than a scoped token, so
   the header/claim parity BE-5 established is asserted for the RBAC fields too
   and not just for `active_tenant_id`.
3. `tests/security/test_tenant_isolation_rls.py` — a member of two workspaces
   sees, from `/me`, only the permissions of the *active* one; switching
   workspace changes the set. This pins the fix as a scoped bind rather than a
   widened policy: a user-keyed policy on `membership_roles` would return both
   workspaces' grants and fail this test.
4. A negative case: `/me` with no workspace resolvable (a user with no
   memberships, or an `X-Tenant-ID` they do not belong to) still returns `200`
   with `active_tenant_id: null` and `permissions: []`, and does not raise
   `TenantContextMissingError`. This is the property that makes `/me` the
   discovery endpoint, and it is the one most at risk from the fix.
