# BuildSEO — Frontend Architecture

Frontend for a multi-tenant SaaS that helps SEO/marketing teams discover, qualify,
manage and submit links to **FREE online listing and directory websites**.

The frontend is a pure presentation + server-state client. All business logic
(RBAC, tenant isolation, publisher qualification, opportunity scoring, submission
rules, credential encryption, AI provider calls) lives in the FastAPI backend.

---

## 1. Complete frontend architecture

```
                        FastAPI  (/api/v1)
                              │  OpenAPI 3.1 schema
                              ▼
              src/types/api.generated.ts   (openapi-typescript)
                              ▼
              src/lib/api/*                (typed API client, one module per resource)
                              ▼
              src/features/*/api/*         (TanStack Query hooks + query keys)
                              ▼
              src/features/*/components    (feature UI)
                              ▼
              src/app/(dashboard)/*        (App Router pages / layouts)
                              ▼
              src/components/ui            (shadcn/ui + Tailwind design tokens)
```

Hard rules enforced by this architecture:

| Rule | Mechanism |
| --- | --- |
| No `fetch()` in components | Only `src/lib/api/http.ts` calls `fetch`. Enforced by ESLint `no-restricted-globals` outside `lib/api`. |
| No DB access | No DB driver is a dependency. |
| No duplicated authorization | `usePermissions()` reads the permission list the backend returns; it gates UX only. |
| No secrets in the browser | Only `NEXT_PUBLIC_*` config exists; provider API keys are write-only fields posted to the backend. |
| No stale tenant data | Every tenant-scoped query key starts `["t", tenantId, …]`; switching tenant removes that scope from the cache. |

### Layer responsibilities

1. **`lib/api/http.ts`** — the only transport. Base URL from env, credentials mode,
   tenant header injection, JSON parsing, `ApiError` normalisation, single-flight
   token refresh with loop protection.
2. **`lib/api/<resource>.ts`** — thin, typed, resource-scoped functions. No React.
3. **`features/<feature>/api/`** — query keys + `useQuery`/`useMutation` hooks,
   cache invalidation, optimistic updates where safe.
4. **`features/<feature>/components/`** — feature UI, table column definitions,
   forms, dialogs.
5. **`app/`** — routing, layouts, metadata, Suspense/error boundaries only.

---

## 2. Folder structure

```
frontend/
├── e2e/                              Playwright specs
├── src/
│   ├── app/
│   │   ├── (auth)/login/page.tsx
│   │   ├── (dashboard)/
│   │   │   ├── layout.tsx            sidebar + header shell, auth guard
│   │   │   ├── dashboard/
│   │   │   ├── websites/{new,[id]}
│   │   │   ├── campaigns/{new,[id]}
│   │   │   ├── publishers/{discovery,[id]}
│   │   │   ├── opportunities/[id]
│   │   │   ├── submissions/[id]
│   │   │   ├── team/
│   │   │   ├── audit/
│   │   │   └── settings/{general,workspace,ai,integrations,roles,security}
│   │   ├── layout.tsx                html shell, providers
│   │   ├── globals.css               Tailwind v4 + design tokens
│   │   ├── not-found.tsx
│   │   └── error.tsx
│   ├── components/
│   │   ├── ui/                       shadcn/ui primitives
│   │   ├── layout/                   AppSidebar, AppHeader, PageHeader, Breadcrumbs
│   │   ├── navigation/               nav tree, WorkspaceSwitcher, UserMenu
│   │   ├── data-table/               DataTable, Toolbar, Pagination, ColumnHeader
│   │   ├── forms/                    Field, FormDialog, form error mapping
│   │   ├── feedback/                 EmptyState, ErrorState, LoadingState, ConfirmDialog
│   │   └── shared/                   StatusBadge, ScoreBadge, MetricCard, ActivityFeed,
│   │                                 ProgressCard, SearchInput, FilterDropdown,
│   │                                 DateRangePicker, PermissionGate
│   ├── features/                     auth, dashboard, websites, campaigns, publishers,
│   │                                 opportunities, submissions, credentials, team,
│   │                                 roles, audit, settings
│   ├── lib/
│   │   ├── api/                      http client + one module per resource
│   │   ├── auth/                     AuthProvider, token store, session lifecycle
│   │   ├── permissions/              PermissionProvider, can(), usePermission()
│   │   ├── tenant/                   TenantProvider, active-tenant persistence
│   │   ├── query/                    QueryClient factory, tenant key helpers
│   │   ├── validation/               shared Zod schemas + server error mapping
│   │   └── utils/                    cn, formatters, debounce, url-state
│   ├── hooks/                        useDebouncedValue, useUrlState, useMediaQuery, …
│   ├── types/                        domain types, api.generated.ts
│   └── config/                       app config, navigation, status maps
├── .env.example
├── vitest.config.ts
├── playwright.config.ts
└── package.json
```

Code is organised **by business feature**, not by technical kind.

---

## 3. Route map

| Route | Purpose | Access |
| --- | --- | --- |
| `/login` | Credential sign-in | Public (SEO metadata lives here) |
| `/dashboard` | KPIs, campaign performance, activity, progress | Authenticated |
| `/websites`, `/websites/new`, `/websites/[id]` | Client website CRUD (API: `/client-websites`) | `client_website.*` |
| `/campaigns`, `/campaigns/new`, `/campaigns/[id]` | Campaigns + 6-step wizard | `campaign.*` |
| `/publishers`, `/publishers/discovery`, `/publishers/[id]` | Publisher database, async discovery, detail | `publisher.*` |
| `/opportunities`, `/opportunities/[id]` | Opportunity workflow + AI content prep | `opportunity.*` |
| `/submissions`, `/submissions/[id]` | Submission review, approval, verification | `submission.*` |
| `/team` | Members | `user.read` |
| `/audit` | Audit log | `audit.read` |
| `/settings` | Settings index | Authenticated |
| `/settings/general` | Preferences (theme, sidebar, page size) | Authenticated |
| `/settings/profile` | The user's own profile | Authenticated |
| `/settings/workspace` | Workspace profile | `tenant.read` |
| `/settings/roles` | Roles & permission matrix | `role.read` |
| `/settings/ai` | BYOK AI providers | `credential.view` |
| `/settings/integrations` | Third-party integrations | `credential.view` |
| `/settings/security` | Sessions / security posture | Authenticated |

Sidebar filtered views are the same routes with URL state, e.g.
`/campaigns?status=active`, `/publishers?status=qualified`,
`/submissions?status=published`, `/opportunities?view=recommended`.
This keeps one canonical table implementation per resource and makes every view
bookmarkable.

`middleware.ts` performs a cheap cookie presence check to redirect
unauthenticated navigations to `/login?next=…`. It is a UX optimisation only —
the backend remains authoritative.

---

## 4. Component hierarchy

```
RootLayout (server)
└── Providers (client)
    ├── ThemeProvider            next-themes, class strategy
    ├── QueryProvider            TanStack Query + Devtools (dev only)
    ├── AuthProvider             session + active tenant + permissions
    │                            (one provider: the access token is
    │                             workspace-scoped and the permission set is
    │                             per-workspace, so all three change together
    │                             atomically — see §7. Consumed through three
    │                             separate hooks: useAuth, useTenant,
    │                             usePermissions.)
    └── Toaster                  sonner

DashboardLayout (client shell)
├── SidebarProvider              collapsed state, localStorage, mobile drawer
│   └── AppSidebar
│       ├── SidebarBrand
│       ├── WorkspaceSwitcher
│       ├── SidebarNav           permission-filtered, collapsible groups, tooltips
│       └── SidebarFooter        sticky: Settings / Profile / Workspace
├── AppHeader
│   ├── SidebarToggle + Breadcrumbs
│   └── WorkspaceSwitcher · NotificationsButton · ThemeToggle · UserMenu
└── <main>
    ├── PageHeader (title, description, actions)
    └── page content
        └── DataTable
            ├── DataTableToolbar   SearchInput, FilterDropdown, ViewOptions
            ├── table
            └── DataTablePagination
```

Shared primitives (never duplicated per feature): `DataTable`,
`DataTableToolbar`, `DataTablePagination`, `DataTableColumnHeader`,
`StatusBadge`, `ScoreBadge`, `MetricCard`, `ProgressCard`, `ActivityFeed`,
`EmptyState`, `ErrorState`, `LoadingState`, `TableSkeleton`, `ConfirmDialog`,
`FormDialog`, `SearchInput`, `FilterDropdown`, `DateRangePicker`,
`PermissionGate`, `PageHeader`, `Breadcrumbs`.

---

## 5. API integration architecture

`src/lib/api/http.ts` exposes `apiRequest<T>()` plus `api.get/post/patch/put/del`.

Responsibilities:

- Base URL: `NEXT_PUBLIC_API_URL` + `/api/v1`.
- `credentials: "include"` so HTTP-only cookie sessions work unchanged.
- `Authorization: Bearer …` added only when a bearer token is held in memory.
- `X-Tenant-ID` header carries the active tenant. The backend re-verifies
  membership; a client-supplied tenant id is never treated as authorization.
- Response handling: 204 → `undefined`; JSON parsed; non-2xx → `ApiError`.
- 401 → single-flight refresh, then one retry. A failed refresh clears session
  state and redirects to `/login`. `_retried` marking + a module-level
  `refreshPromise` prevent infinite refresh loops.
- Request timeouts + `AbortSignal` support; aborts are not surfaced as errors.

Resource modules: `auth.ts`, `tenants.ts`, `users.ts`, `campaigns.ts`,
`publishers.ts`, `opportunities.ts`, `submissions.ts`, `credentials.ts`,
`websites.ts`, `roles.ts`, `audit.ts`, `dashboard.ts`, `ai.ts`.

### Error abstraction (§56)

```ts
class ApiError extends Error {
  status: number            // HTTP status, 0 for network failure
  code: string              // backend machine code, e.g. PUBLISHER_NOT_FOUND
  message: string           // user-facing message
  details?: FieldIssue[]    // normalised from FastAPI/Pydantic 422 `detail`
}
```

A single `ERROR_MESSAGES` map turns backend codes and statuses into
user-friendly copy. Backend stack traces and raw `detail` strings are never
rendered.

### Missing endpoints (§70)

No mock API is shipped. When the backend does not yet expose an endpoint, the
typed client method is still written against the documented contract and the gap
is recorded in `docs/API_CONTRACT.md`. Nothing fabricates a successful response.

---

## 6. Authentication / token architecture

The backend issues **bearer tokens, not cookies**. `POST /auth/login` returns a
`TokenPair` in the response body: a short-lived JWT access token and a
long-lived **opaque refresh token**.

That refresh token must not go into `localStorage`, where any script on the
page could read it. So the frontend runs a thin session BFF — three Next.js
route handlers that proxy the three token-bearing calls:

```
browser                    Next.js route handler              FastAPI
   │  POST /api/session/login  │                                 │
   ├──────────────────────────►│  POST /api/v1/auth/login        │
   │                           ├────────────────────────────────►│
   │                           │◄── { access_token, refresh_token }
   │   { access_token }        │  Set-Cookie: buildseo_rt        │
   │◄──────────────────────────┤    HttpOnly; SameSite=Strict    │
   │                                                             │
   │  every other request: Authorization: Bearer <in-memory>      │
   ├─────────────────────────────────────────────────────────────►│
```

- **Access token: memory only** (`lib/api/token-store.ts`). Never
  `localStorage`, `sessionStorage`, a global store, or a log line. A page
  reload starts with none.
- **Refresh token: HTTP-only cookie**, readable only by the Next.js server.
  It never enters JavaScript.
- **Cold load**: `AuthProvider` calls `/api/session/refresh` once; the cookie
  mints a fresh access token, or the user is treated as signed out.
- **"Remember this session"** controls the refresh cookie's lifetime —
  persistent (14 days, matching the backend's refresh TTL) versus a session
  cookie dropped on browser close. The backend has no such flag, so this is
  honestly a frontend concern and nothing is persisted to fake it.
- **401 handling**: one single-flight refresh, then one retry. A `_retried`
  marker plus a module-level `refreshPromise` make an infinite refresh loop
  structurally impossible. A failed refresh clears state and redirects to
  `/login?next=…` exactly once.
- **Network failure during refresh does not sign the user out**: the cookie is
  kept and the error surfaces as a retryable network error, so a connectivity
  blip cannot end a valid session.
- **Login states**: `idle | submitting | success | error`, with separate copy
  for an authentication failure versus a network failure, and no backend
  internals shown. Authentication failures do not distinguish "unknown account"
  from "wrong password" — neither does the backend, and doing so would enable
  account enumeration.
- `?next=` is honoured only for same-origin relative paths, so the login page
  cannot be turned into an open redirect.
- Password reset and email verification are absent (§14), and `lib/api/auth.ts`
  is shaped so they drop in without touching call sites.

## 7. Tenant-switching architecture

```
switchTenant(id)
  → POST /auth/select-tenant          new access token, scoped to the workspace
  → queryClient.removeQueries({ predicate: isTenantScoped })
  → queryClient.removeQueries({ queryKey: ["session"] })
  → setActiveTenantId(id); tenantVersion++
  → session refetches → new permission set
  → tenant-scoped queries remount and refetch
```

Why session, tenant and permissions live in one provider: the backend's access
token carries a `tid` claim and `/me` computes permissions for *that* workspace.
"Who am I", "which workspace" and "what may I do" therefore change in one
atomic step. Splitting them across providers would open a window in which one
workspace's rows render against another workspace's permissions. The three
slices are still consumed separately — `useAuth`, `useTenant`,
`usePermissions` — so feature code depends only on what it needs.

Four mechanisms make the isolation structural rather than careful:

1. **The `"t"` sentinel.** Every workspace-owned key is built by
   `tenantKey(tenantId, …)` → `["t", tenantId, …]`. `isTenantScopedKey` then
   identifies exactly those entries, so global keys (session, workspace list)
   provably survive a switch.
2. **Remove, don't invalidate.** Invalidated queries keep serving stale data
   while refetching. Removed ones have nothing to serve, so no component can
   render the previous workspace's rows during the gap.
3. **`TenantScope`** keys the content region on `activeTenantId:tenantVersion`.
   Clearing the cache does not clear React state — a table's selected rows, an
   open dialog, a half-filled wizard — and remounting is the only reliable way
   to discard all of it at once.
4. **`enabled: Boolean(tenantId)`** on every workspace-scoped query, so no
   request is ever made without a workspace (which the backend would reject
   with `TENANT_CONTEXT_REQUIRED`).

The active workspace is remembered per user (`buildseo:active-tenant:<userId>`)
so two accounts on one browser do not inherit each other's choice, and it is
dropped if the user is no longer a member of it.

## 8. RBAC / permission UI architecture

```ts
const { can, canAny, canAll } = usePermissions();
can("publisher.create");
```

- The permission list comes from the backend (`/auth/me` → `permissions`), never
  hardcoded per role in the client.
- `<PermissionGate permission="campaign.create">` hides or disables actions
  (`mode="hide" | "disable"`), with an optional `fallback`.
- Navigation items declare a required permission and are filtered before render.
- Route-level UX guard renders a "no access" state instead of a broken page.
- Wildcards (`publisher.*`, `*`) are supported so backend-defined superuser
  roles work without client changes.
- This is **UX only**; the FastAPI layer enforces authorization.

---

## 9. TanStack Query architecture

- One `QueryClient` per browser session, created in a client provider.
- Defaults: `staleTime` 30s, `gcTime` 5min, `retry` — never for 4xx, up to 2 for
  5xx/network, `refetchOnWindowFocus` false (dense B2B tables).
- `throwOnError` is off; every screen renders an `ErrorState` with retry.
- Query keys (§16):

```ts
["session"]
["t", tenantId, "campaigns", { list: filters }]
["t", tenantId, "campaigns", { detail: id }]
["t", tenantId, "publishers", { list: filters }]
["t", tenantId, "opportunities", { list: { campaignId, ...filters } }]
["t", tenantId, "submissions", { list: filters }]
["t", tenantId, "dashboard", "summary"]
```

- Mutations invalidate the narrowest correct scope; list + detail invalidation is
  co-located with the mutation hook.
- Optimistic updates are used only for preference/simple-toggle mutations (§55) —
  never for submission creation, qualification, campaign creation or credentials.
- Long-running discovery uses backend job polling (`refetchInterval` while the
  job is not terminal), never a blocking request.

---

## 10. State management strategy

| State | Home |
| --- | --- |
| Server data | TanStack Query |
| Auth session | `AuthProvider` (memory + HTTP-only cookies) |
| Active tenant | `TenantProvider` (+ per-user `localStorage` key) |
| Permissions | `PermissionProvider`, derived from session |
| Table filters / search / pagination | **URL query params** (`useUrlState`) |
| Sidebar collapsed, theme, table density | `localStorage` via small hooks |
| Ephemeral UI (dialogs, wizard step) | local `useState` |

No Redux/Zustand global store. Nothing that belongs in the URL is duplicated in
React state.

---

## 11. Type generation from FastAPI OpenAPI

**This is in place, not aspirational.** `src/types/api.generated.ts` (11k lines)
was produced from the running backend's OpenAPI document and is committed.

```bash
npm run codegen:api    # openapi-typescript $API_SCHEMA_URL -o src/types/api.generated.ts
npm run typecheck      # every drift site becomes a compile error
```

`API_SCHEMA_URL` defaults to `http://localhost:8000/openapi.json`. Regenerating
without a running backend is also possible:

```bash
cd backend && python -c "
import json; from app.main import create_app
json.dump(create_app().openapi(), open('openapi.json','w'))"
```

Nothing in the application imports `api.generated.ts` directly. Every domain
type is an alias in `src/types/api.ts`:

```ts
export type Campaign = Schemas["CampaignRead"];
export type PublisherStatus = Schemas["PublisherStatus"];
```

Two deliberate refinements sit on top of the generated types:

- **`WithOptional<T, K>`** — a Pydantic field with a default is absent from the
  schema's `required` array, but `openapi-typescript` still emits it as
  required. That is right for a response and wrong for a request, so the
  request types re-open exactly those fields.
- **`config/enums.ts`** — the generated enums are compile-time unions, but
  filter dropdowns need iterable values. `allOf<Union>()([...])` returns the
  list unchanged and type-checks only when it covers the union *exactly*, so a
  backend enum change fails the build rather than shipping a filter that
  silently omits a status.

Workflow on a backend schema change: `npm run codegen:api` → `npm run typecheck`
→ fix the flagged call sites → commit the regenerated file.

## 12. Responsive layout strategy

| Breakpoint | Behaviour |
| --- | --- |
| `≥1280px` | Expanded sidebar (16rem) + full tables |
| `1024–1279px` | Sidebar collapsible to icon rail (3.5rem) with tooltips |
| `768–1023px` | Sidebar defaults to the icon rail |
| `<768px` | Sidebar becomes a Sheet drawer; tables switch to stacked record cards |

Implemented with Tailwind breakpoints + one CSS-variable-driven sidebar width, so
collapsing is a class/attribute change with no route change and no remount.
`DataTable` takes a `mobileRow` renderer; where none is supplied the table gets a
bounded horizontal scroll container instead of breaking the page layout.

---

## 13. Testing strategy

**Vitest + React Testing Library** (`jsdom`) — unit and component:

- API client: error normalisation, 422 → field errors, 401 refresh-once,
  refresh-loop protection.
- Auth: login success/failure/network, logout, expired-session redirect.
- Tenant: switch clears tenant-scoped cache, keeps global cache, refetches
  permissions, never renders previous-tenant rows.
- Permissions: `can()` incl. wildcards, `PermissionGate` hide/disable,
  navigation filtering.
- URL state, debounce, formatters, status/score badges.
- Forms: Zod validation, server 422 mapping to field errors, submit states.
- Feature smoke tests: campaign create, publisher filter/paginate, opportunity
  approve, submission approve/reject.

**Playwright** (`e2e/`) — the full workflow:

```
login → select workspace → campaigns → create campaign → discover publishers
      → review opportunities → prepare submission → approve → verify status
```

plus a restricted-permission scenario asserting a user without
`submission.approve` cannot reach or trigger the action. E2E specs run against a
real backend (`E2E_BASE_URL`), and are skipped rather than mocked when it is
absent, so no fake backend behaviour ever enters the suite.

**Commands**

```bash
npm run typecheck   # tsc --noEmit, strict
npm run lint        # eslint
npm run test        # vitest run
npm run test:e2e    # playwright
npm run build       # next build
```

---

## 14. MVP scope guardrails

The product supports **free directory / listing links only**. There is no UI for
paid placements, guest-post marketplaces, sponsored links, link buying, email
outreach, link exchanges, PBNs or forum/comment posting, and no email sending of
any kind. Scope is surfaced in-product via a `FREE LISTINGS ONLY` badge on
campaign creation and opportunity screens.

Future modules (guest posts, editorial outreach, digital PR, link monitoring,
competitor backlink intelligence, AI agents) are accommodated by the
feature-folder + navigation-config architecture: a new module is a new
`features/<module>` folder plus one entry in `config/navigation.ts`. None are
implemented now.
