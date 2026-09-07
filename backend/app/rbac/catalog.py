"""The permission catalog and the default role definitions.

Two things live here and nowhere else:

1. Every permission code the platform recognises. The catalog is the single
   source of truth used by the seed script, the ``/permissions`` endpoint and
   the ``require_permission`` dependency, so a typo becomes an import error
   rather than a silently unenforced route.
2. What each seeded role grants. Roles are seeded *per tenant* (a copy per
   workspace), so a tenant can edit its own roles without affecting anyone
   else, and custom roles need no schema change.

``Perm`` is a ``StrEnum``, so ``require_permission(Perm.PUBLISHER_CREATE)``
is checked by the type checker while still comparing equal to the string
stored in the database.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.core.enums import SystemRoleSlug


class Perm(StrEnum):
    """Every recognised permission code, as ``resource.action``."""

    # --- tenant ---------------------------------------------------------- #
    TENANT_READ = "tenant.read"
    TENANT_UPDATE = "tenant.update"
    TENANT_DELETE = "tenant.delete"
    TENANT_TRANSFER_OWNERSHIP = "tenant.transfer_ownership"

    # --- users and membership -------------------------------------------- #
    USER_READ = "user.read"
    USER_CREATE = "user.create"
    USER_UPDATE = "user.update"
    USER_DELETE = "user.delete"

    # --- RBAC ------------------------------------------------------------ #
    ROLE_READ = "role.read"
    ROLE_CREATE = "role.create"
    ROLE_UPDATE = "role.update"
    ROLE_DELETE = "role.delete"
    PERMISSION_READ = "permission.read"

    # --- client websites -------------------------------------------------- #
    CLIENT_WEBSITE_READ = "client_website.read"
    CLIENT_WEBSITE_CREATE = "client_website.create"
    CLIENT_WEBSITE_UPDATE = "client_website.update"
    CLIENT_WEBSITE_DELETE = "client_website.delete"

    # --- campaigns -------------------------------------------------------- #
    CAMPAIGN_READ = "campaign.read"
    CAMPAIGN_CREATE = "campaign.create"
    CAMPAIGN_UPDATE = "campaign.update"
    CAMPAIGN_DELETE = "campaign.delete"

    # --- publishers ------------------------------------------------------- #
    PUBLISHER_READ = "publisher.read"
    PUBLISHER_CREATE = "publisher.create"
    PUBLISHER_UPDATE = "publisher.update"
    PUBLISHER_DELETE = "publisher.delete"
    PUBLISHER_DISCOVER = "publisher.discover"
    PUBLISHER_QUALIFY = "publisher.qualify"

    # --- opportunities ---------------------------------------------------- #
    OPPORTUNITY_READ = "opportunity.read"
    OPPORTUNITY_CREATE = "opportunity.create"
    OPPORTUNITY_UPDATE = "opportunity.update"
    OPPORTUNITY_DELETE = "opportunity.delete"

    # --- submissions ------------------------------------------------------ #
    SUBMISSION_READ = "submission.read"
    SUBMISSION_CREATE = "submission.create"
    SUBMISSION_UPDATE = "submission.update"
    SUBMISSION_DELETE = "submission.delete"
    #: Separated from ``submission.update`` on purpose: approving is the
    #: human-in-the-loop gate, so a specialist can prepare a submission
    #: without being able to authorise it.
    SUBMISSION_APPROVE = "submission.approve"
    SUBMISSION_VERIFY = "submission.verify"

    # --- credentials (BYOK) ----------------------------------------------- #
    CREDENTIAL_READ = "credential.read"
    CREDENTIAL_CREATE = "credential.create"
    CREDENTIAL_UPDATE = "credential.update"
    CREDENTIAL_DELETE = "credential.delete"

    # --- integrations and AI ---------------------------------------------- #
    INTEGRATION_READ = "integration.read"
    INTEGRATION_CREATE = "integration.create"
    INTEGRATION_UPDATE = "integration.update"
    INTEGRATION_DELETE = "integration.delete"
    AI_GENERATE = "ai.generate"
    AI_USAGE_READ = "ai.usage_read"

    # --- operations -------------------------------------------------------- #
    AUDIT_READ = "audit.read"
    JOB_READ = "job.read"
    JOB_CREATE = "job.create"

    @property
    def resource(self) -> str:
        return self.value.split(".", 1)[0]

    @property
    def action(self) -> str:
        return self.value.split(".", 1)[1]


@dataclass(frozen=True, slots=True)
class PermissionSpec:
    """A catalog entry: the code plus the description shown in the UI."""

    permission: Perm
    description: str

    @property
    def code(self) -> str:
        return self.permission.value

    @property
    def resource(self) -> str:
        return self.permission.resource

    @property
    def action(self) -> str:
        return self.permission.action


PERMISSION_CATALOG: tuple[PermissionSpec, ...] = (
    PermissionSpec(Perm.TENANT_READ, "View workspace settings and details"),
    PermissionSpec(Perm.TENANT_UPDATE, "Change workspace settings"),
    PermissionSpec(Perm.TENANT_DELETE, "Archive or delete the workspace"),
    PermissionSpec(Perm.TENANT_TRANSFER_OWNERSHIP, "Transfer workspace ownership"),
    PermissionSpec(Perm.USER_READ, "View workspace members"),
    PermissionSpec(Perm.USER_CREATE, "Add a member to the workspace"),
    PermissionSpec(Perm.USER_UPDATE, "Change a member's status or roles"),
    PermissionSpec(Perm.USER_DELETE, "Remove a member from the workspace"),
    PermissionSpec(Perm.ROLE_READ, "View roles and their permissions"),
    PermissionSpec(Perm.ROLE_CREATE, "Create a custom role"),
    PermissionSpec(Perm.ROLE_UPDATE, "Change a custom role's permissions"),
    PermissionSpec(Perm.ROLE_DELETE, "Delete a custom role"),
    PermissionSpec(Perm.PERMISSION_READ, "View the permission catalog"),
    PermissionSpec(Perm.CLIENT_WEBSITE_READ, "View client websites"),
    PermissionSpec(Perm.CLIENT_WEBSITE_CREATE, "Add a client website"),
    PermissionSpec(Perm.CLIENT_WEBSITE_UPDATE, "Edit a client website"),
    PermissionSpec(Perm.CLIENT_WEBSITE_DELETE, "Delete a client website"),
    PermissionSpec(Perm.CAMPAIGN_READ, "View campaigns"),
    PermissionSpec(Perm.CAMPAIGN_CREATE, "Create a campaign"),
    PermissionSpec(Perm.CAMPAIGN_UPDATE, "Edit a campaign"),
    PermissionSpec(Perm.CAMPAIGN_DELETE, "Delete a campaign"),
    PermissionSpec(Perm.PUBLISHER_READ, "View publishers"),
    PermissionSpec(Perm.PUBLISHER_CREATE, "Add a publisher"),
    PermissionSpec(Perm.PUBLISHER_UPDATE, "Edit a publisher"),
    PermissionSpec(Perm.PUBLISHER_DELETE, "Delete a publisher"),
    PermissionSpec(Perm.PUBLISHER_DISCOVER, "Run publisher discovery"),
    PermissionSpec(Perm.PUBLISHER_QUALIFY, "Run publisher qualification and scoring"),
    PermissionSpec(Perm.OPPORTUNITY_READ, "View link opportunities"),
    PermissionSpec(Perm.OPPORTUNITY_CREATE, "Create link opportunities"),
    PermissionSpec(Perm.OPPORTUNITY_UPDATE, "Edit or advance link opportunities"),
    PermissionSpec(Perm.OPPORTUNITY_DELETE, "Delete link opportunities"),
    PermissionSpec(Perm.SUBMISSION_READ, "View submissions"),
    PermissionSpec(Perm.SUBMISSION_CREATE, "Prepare a submission"),
    PermissionSpec(Perm.SUBMISSION_UPDATE, "Edit or advance a submission"),
    PermissionSpec(Perm.SUBMISSION_DELETE, "Delete a submission"),
    PermissionSpec(Perm.SUBMISSION_APPROVE, "Approve a submission for sending"),
    PermissionSpec(Perm.SUBMISSION_VERIFY, "Verify a published link"),
    PermissionSpec(Perm.CREDENTIAL_READ, "View configured provider credentials (metadata only)"),
    PermissionSpec(Perm.CREDENTIAL_CREATE, "Add a provider credential"),
    PermissionSpec(Perm.CREDENTIAL_UPDATE, "Replace or disable a provider credential"),
    PermissionSpec(Perm.CREDENTIAL_DELETE, "Delete a provider credential"),
    PermissionSpec(Perm.INTEGRATION_READ, "View integration configuration"),
    PermissionSpec(Perm.INTEGRATION_CREATE, "Add an integration configuration"),
    PermissionSpec(Perm.INTEGRATION_UPDATE, "Change an integration configuration"),
    PermissionSpec(Perm.INTEGRATION_DELETE, "Remove an integration configuration"),
    PermissionSpec(Perm.AI_GENERATE, "Generate listing content with AI"),
    PermissionSpec(Perm.AI_USAGE_READ, "View AI usage and cost accounting"),
    PermissionSpec(Perm.AUDIT_READ, "Read the audit trail"),
    PermissionSpec(Perm.JOB_READ, "View background jobs"),
    PermissionSpec(Perm.JOB_CREATE, "Enqueue background jobs"),
)

ALL_PERMISSIONS: frozenset[Perm] = frozenset(spec.permission for spec in PERMISSION_CATALOG)


@dataclass(frozen=True, slots=True)
class RoleDefinition:
    """A seeded role: its slug, display name and permission set."""

    slug: SystemRoleSlug
    name: str
    description: str
    permissions: frozenset[Perm]


def _read_only(*resources: str) -> frozenset[Perm]:
    """Every ``<resource>.read`` permission for the given resources."""
    wanted = set(resources)
    return frozenset(
        perm for perm in ALL_PERMISSIONS if perm.resource in wanted and perm.action == "read"
    )


def _all_for(*resources: str) -> frozenset[Perm]:
    """Every permission for the given resources."""
    wanted = set(resources)
    return frozenset(perm for perm in ALL_PERMISSIONS if perm.resource in wanted)


#: Ownership-level operations. Held by Owner alone: an Admin can run the
#: workspace day to day but cannot delete it or hand it to someone else.
_OWNERSHIP_ONLY: frozenset[Perm] = frozenset({Perm.TENANT_DELETE, Perm.TENANT_TRANSFER_OWNERSHIP})

_MANAGER_PERMISSIONS: frozenset[Perm] = (
    _all_for("client_website", "campaign", "publisher", "opportunity", "submission")
    | {Perm.AI_GENERATE, Perm.AI_USAGE_READ, Perm.JOB_READ, Perm.JOB_CREATE}
    | _read_only("tenant", "user", "role", "permission", "credential", "integration")
)

#: A specialist works the queue: prepare and advance, but never approve, never
#: delete, and no access to credentials at all. It includes the same member and
#: role reads a Viewer gets so the privilege ladder nests
#: (viewer < specialist < manager < admin < owner); otherwise promoting a
#: Viewer to Specialist would silently take visibility away.
_SPECIALIST_PERMISSIONS: frozenset[Perm] = _read_only(
    "tenant",
    "user",
    "role",
    "permission",
    "client_website",
    "campaign",
    "publisher",
    "opportunity",
    "submission",
) | {
    Perm.OPPORTUNITY_CREATE,
    Perm.OPPORTUNITY_UPDATE,
    Perm.SUBMISSION_CREATE,
    Perm.SUBMISSION_UPDATE,
    Perm.PUBLISHER_CREATE,
    Perm.PUBLISHER_UPDATE,
    Perm.PUBLISHER_QUALIFY,
    Perm.AI_GENERATE,
    Perm.JOB_READ,
}

#: Read-only, and deliberately excluding credential and audit reads: both are
#: sensitive surfaces that a general viewer has no need for.
_VIEWER_PERMISSIONS: frozenset[Perm] = _read_only(
    "tenant",
    "user",
    "role",
    "permission",
    "client_website",
    "campaign",
    "publisher",
    "opportunity",
    "submission",
)

DEFAULT_ROLE_DEFINITIONS: tuple[RoleDefinition, ...] = (
    RoleDefinition(
        slug=SystemRoleSlug.OWNER,
        name="Owner",
        description="Full access to the workspace, including ownership transfer and deletion.",
        permissions=ALL_PERMISSIONS,
    ),
    RoleDefinition(
        slug=SystemRoleSlug.ADMIN,
        name="Admin",
        description=(
            "Administrative access to everything except ownership-level operations "
            "(deleting the workspace or transferring ownership)."
        ),
        permissions=ALL_PERMISSIONS - _OWNERSHIP_ONLY,
    ),
    RoleDefinition(
        slug=SystemRoleSlug.SEO_MANAGER,
        name="SEO Manager",
        description=(
            "Runs the full campaign, publisher, opportunity and submission lifecycle, "
            "including submission approval. Read-only on members, roles and credentials."
        ),
        permissions=_MANAGER_PERMISSIONS,
    ),
    RoleDefinition(
        slug=SystemRoleSlug.SEO_SPECIALIST,
        name="SEO Specialist",
        description=(
            "Works assigned campaigns and the submission queue. Cannot approve "
            "submissions, delete records, or access credentials."
        ),
        permissions=_SPECIALIST_PERMISSIONS,
    ),
    RoleDefinition(
        slug=SystemRoleSlug.VIEWER,
        name="Viewer",
        description="Read-only access. Excludes credentials and the audit trail.",
        permissions=_VIEWER_PERMISSIONS,
    ),
)


def permissions_for_role(slug: str) -> frozenset[Perm]:
    """Permissions granted by a seeded role.

    Raises:
        KeyError: ``slug`` is not one of the seeded system roles. Custom roles
            carry their permissions in the database, not here.
    """
    for definition in DEFAULT_ROLE_DEFINITIONS:
        if definition.slug.value == slug:
            return definition.permissions
    raise KeyError(f"unknown system role: {slug}")
