"""Aggregation of every ``/api/v1`` router.

Routers are registered here rather than in ``main`` so the API surface is
reviewable in one file, and so the tag order below drives the ordering of
sections in the generated OpenAPI docs.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    ai,
    audit,
    auth,
    campaigns,
    client_websites,
    credentials,
    jobs,
    me,
    opportunities,
    publishers,
    rbac,
    submissions,
    tenants,
    users,
)

api_router = APIRouter()

# Registration order shapes the OpenAPI document. It also matters for routing:
# a router with static paths that could shadow another's path parameters must
# come first (see the note on publishers/opportunities/submissions below).
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(tenants.router)
api_router.include_router(users.router)
api_router.include_router(rbac.router)
api_router.include_router(client_websites.router)
api_router.include_router(campaigns.router)
# These three declare static sub-paths (/publishers/discovery-runs,
# /opportunities/state-machine, /submissions/review-queue) alongside
# /{id} routes. FastAPI matches in declaration order and each router declares
# its static paths before its parameterised ones, so "discovery-runs" is never
# parsed as a UUID.
api_router.include_router(publishers.router)
api_router.include_router(opportunities.router)
api_router.include_router(submissions.router)
api_router.include_router(credentials.router)
api_router.include_router(ai.router)
api_router.include_router(audit.router)
api_router.include_router(jobs.router)

#: Drives section ordering and descriptions in the OpenAPI document.
OPENAPI_TAGS: list[dict[str, str]] = [
    {"name": "Health", "description": "Liveness, readiness and service health probes."},
    {
        "name": "Authentication",
        "description": (
            "Registration, login, refresh-token rotation, logout, session management "
            "and active-tenant selection."
        ),
    },
    {"name": "Users", "description": "The authenticated user's profile and tenant memberships."},
    {"name": "Tenants", "description": "Workspace administration and membership management."},
    {"name": "RBAC", "description": "Roles, role-permission mapping and the permission catalog."},
    {
        "name": "Client Websites",
        "description": "The client sites and projects a tenant promotes.",
    },
    {"name": "Campaigns", "description": "Free-listing link campaigns for a client website."},
    {
        "name": "Publishers",
        "description": (
            "Candidate free listing and directory sites, their discovery and their "
            "qualification scores."
        ),
    },
    {
        "name": "Opportunities",
        "description": "Campaign-to-publisher listing opportunities and their lifecycle.",
    },
    {
        "name": "Submissions",
        "description": "Human-reviewed submission workflow and link verification.",
    },
    {
        "name": "Credentials",
        "description": (
            "Bring-your-own-key provider credentials. Secrets are encrypted at rest "
            "and never returned."
        ),
    },
    {"name": "AI", "description": "Per-tenant AI provider configuration and usage accounting."},
    {"name": "Audit", "description": "Security and business audit trail."},
    {"name": "Jobs", "description": "Background job inspection."},
]
