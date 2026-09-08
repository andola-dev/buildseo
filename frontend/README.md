# BuildSEO — Frontend

Next.js 15 + React 19 frontend for a multi-tenant SaaS that helps SEO teams
discover, qualify, manage and submit links to **free online listing and
directory websites**.

It is a presentation + server-state client only. All business logic — RBAC,
tenant isolation, publisher qualification, opportunity scoring, submission
rules, credential encryption, AI provider calls — belongs to the FastAPI
backend, which stays the source of truth.

## Stack

React 19 · Next.js 15 (App Router) · TypeScript (strict) · Tailwind CSS v4 ·
shadcn/ui · TanStack Query · TanStack Table · Zod · Lucide · Vitest +
React Testing Library · Playwright.

## Getting started

```bash
cp .env.example .env.local     # point NEXT_PUBLIC_API_URL at the backend
npm install
npm run dev                    # http://localhost:3000
```

The backend must be reachable at `NEXT_PUBLIC_API_URL` (default
`http://localhost:8000`) and must allow this origin in `CORS_ORIGINS`.

## Commands

| Command | What it does |
| --- | --- |
| `npm run dev` | Development server |
| `npm run build` / `npm start` | Production build and serve |
| `npm run typecheck` | `tsc --noEmit`, strict |
| `npm run lint` | ESLint |
| `npm run test` | Vitest unit + component tests |
| `npm run test:e2e` | Playwright end-to-end suite |
| `npm run codegen:api` | Regenerate API types from the backend's OpenAPI document |

## API types are generated

`src/types/api.generated.ts` is produced from the backend's OpenAPI document
and committed. Never edit it by hand.

```bash
# with the backend running
npm run codegen:api && npm run typecheck
```

Every domain type is an alias into it (`src/types/api.ts`), so a backend schema
change surfaces as a compile error at each call site rather than drifting
silently. `src/config/enums.ts` additionally checks at compile time that the
runtime enum lists cover each generated union exactly.

`API_SCHEMA_URL` selects the schema source (default
`http://localhost:8000/openapi.json`).

## Running the E2E suite

The Playwright specs run against a **real backend** and mock nothing — a suite
asserting against a fake API proves nothing about the contract. Specs that need
an account skip, with a reason, when the environment is not configured:

```bash
E2E_BASE_URL=http://localhost:3000 \
E2E_EMAIL=you@example.com E2E_PASSWORD='…' \
E2E_WORKSPACE='Acme Marketing' \
npm run test:e2e
```

Optional: `E2E_VIEWER_EMAIL` / `E2E_VIEWER_PASSWORD` for a restricted account,
which enables the RBAC spec. `PLAYWRIGHT_CHROMIUM_PATH` points at a
pre-installed Chromium when the image ships one.

> **Known blocker.** As committed, the backend cannot resolve tenant context —
> every workspace-scoped request returns 403 and the workspace list comes back
> empty. The workflow specs therefore cannot pass yet, and `signIn` fails with
> a message naming the defect so it is not mistaken for a frontend regression.
> Root cause, evidence and the fix are in
> [`docs/BACKEND_DEFECTS.md`](../docs/BACKEND_DEFECTS.md) (BE-1).

## Documentation

- [`docs/FRONTEND_ARCHITECTURE.md`](../docs/FRONTEND_ARCHITECTURE.md) —
  architecture, folder structure, route map, component hierarchy, auth/tenant/
  RBAC/query design, responsive and testing strategy.
- [`docs/API_CONTRACT.md`](../docs/API_CONTRACT.md) — the verified backend
  contract, the details codegen cannot express, and the known gaps.
- [`docs/BACKEND_DEFECTS.md`](../docs/BACKEND_DEFECTS.md) — defects found while
  integrating, with reproduction steps and suggested fixes. Written to be
  handed to whoever works on the backend.

## Scope

Free directory and listing links only. There is no UI for paid placements,
guest-post marketplaces, sponsored links, link buying, email outreach, link
exchanges, PBNs or forum/comment posting, and the product sends no email of any
kind. `FREE LISTINGS ONLY` is surfaced in-product wherever campaigns and
opportunities are created.
