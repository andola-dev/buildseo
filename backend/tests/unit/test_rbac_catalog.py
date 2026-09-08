"""The permission catalog and the seeded role definitions."""

from __future__ import annotations

import pytest

from app.core.enums import SystemRoleSlug
from app.rbac.catalog import (
    ALL_PERMISSIONS,
    DEFAULT_ROLE_DEFINITIONS,
    PERMISSION_CATALOG,
    Perm,
    permissions_for_role,
)

pytestmark = pytest.mark.unit


class TestCatalogIntegrity:
    def test_every_permission_has_exactly_one_catalog_entry(self) -> None:
        codes = [spec.code for spec in PERMISSION_CATALOG]
        assert len(codes) == len(set(codes))
        assert set(Perm) == {spec.permission for spec in PERMISSION_CATALOG}
        assert len(ALL_PERMISSIONS) == len(list(Perm))

    def test_codes_match_their_resource_and_action(self) -> None:
        for spec in PERMISSION_CATALOG:
            assert spec.code == f"{spec.resource}.{spec.action}"

    def test_every_permission_is_described(self) -> None:
        # The descriptions drive the permission matrix in the UI.
        for spec in PERMISSION_CATALOG:
            assert spec.description and spec.description[0].isupper()

    def test_permission_parts_are_derivable(self) -> None:
        assert Perm.PUBLISHER_CREATE.resource == "publisher"
        assert Perm.PUBLISHER_CREATE.action == "create"


class TestRoleDefinitions:
    def test_the_five_default_roles_are_defined_in_order(self) -> None:
        assert [definition.slug for definition in DEFAULT_ROLE_DEFINITIONS] == [
            SystemRoleSlug.OWNER,
            SystemRoleSlug.ADMIN,
            SystemRoleSlug.SEO_MANAGER,
            SystemRoleSlug.SEO_SPECIALIST,
            SystemRoleSlug.VIEWER,
        ]

    def test_owner_holds_everything(self) -> None:
        assert permissions_for_role("owner") == ALL_PERMISSIONS

    def test_admin_is_owner_minus_ownership_level_operations(self) -> None:
        assert permissions_for_role("admin") == ALL_PERMISSIONS - {
            Perm.TENANT_DELETE,
            Perm.TENANT_TRANSFER_OWNERSHIP,
        }

    def test_role_permission_sets_nest_strictly(self) -> None:
        # Promoting a member must never take away visibility they already had.
        viewer = permissions_for_role("viewer")
        specialist = permissions_for_role("seo_specialist")
        manager = permissions_for_role("seo_manager")
        admin = permissions_for_role("admin")
        owner = permissions_for_role("owner")
        assert viewer < specialist < manager < admin < owner

    def test_manager_runs_the_lifecycle_but_administers_nothing(self) -> None:
        manager = permissions_for_role("seo_manager")
        assert {
            Perm.CAMPAIGN_CREATE,
            Perm.PUBLISHER_DELETE,
            Perm.SUBMISSION_APPROVE,
            Perm.SUBMISSION_VERIFY,
            Perm.AI_GENERATE,
            Perm.CREDENTIAL_READ,
        } <= manager
        assert not (
            {Perm.CREDENTIAL_CREATE, Perm.ROLE_CREATE, Perm.USER_DELETE, Perm.TENANT_UPDATE}
            & manager
        )

    def test_specialist_can_prepare_work_but_not_authorise_it(self) -> None:
        # Separation of duties: preparing a submission and approving it are
        # different permissions.
        specialist = permissions_for_role("seo_specialist")
        assert {
            Perm.OPPORTUNITY_UPDATE,
            Perm.SUBMISSION_CREATE,
            Perm.SUBMISSION_UPDATE,
            Perm.PUBLISHER_QUALIFY,
            Perm.AI_GENERATE,
        } <= specialist
        assert Perm.SUBMISSION_APPROVE not in specialist

    def test_specialist_cannot_delete_or_touch_credentials(self) -> None:
        specialist = permissions_for_role("seo_specialist")
        assert not (
            {
                Perm.SUBMISSION_DELETE,
                Perm.OPPORTUNITY_DELETE,
                Perm.PUBLISHER_DELETE,
                Perm.CREDENTIAL_READ,
                Perm.AUDIT_READ,
            }
            & specialist
        )

    def test_viewer_is_read_only(self) -> None:
        assert all(perm.action == "read" for perm in permissions_for_role("viewer"))

    def test_viewer_cannot_see_credentials_the_audit_trail_or_ai_spend(self) -> None:
        assert not (
            {Perm.CREDENTIAL_READ, Perm.AUDIT_READ, Perm.AI_USAGE_READ}
            & permissions_for_role("viewer")
        )

    def test_unknown_role_raises(self) -> None:
        # Custom roles carry their permissions in the database, not here.
        with pytest.raises(KeyError):
            permissions_for_role("not-a-system-role")
