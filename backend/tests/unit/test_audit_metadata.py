"""Audit metadata sanitisation.

The allow-list is the mechanism that keeps secrets out of the audit trail, so
these tests check both halves: only permitted keys survive, and a permitted
key carrying secret-shaped text is still scrubbed.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.audit.actions import (
    METADATA_ALLOWLIST,
    AuditAction,
    allowed_metadata_fields,
    sanitize_metadata,
)
from app.config.logging import REDACTED, SENSITIVE_KEY_PARTS

pytestmark = pytest.mark.unit


class TestAllowList:
    def test_no_action_permits_a_secret_shaped_field_name(self) -> None:
        for action, fields in METADATA_ALLOWLIST.items():
            offending = [
                field
                for field in fields
                if any(part in field.lower() for part in SENSITIVE_KEY_PARTS)
            ]
            assert not offending, f"{action}: {offending}"

    @pytest.mark.parametrize("action", list(AuditAction))
    def test_every_action_permits_the_common_fields(self, action: AuditAction) -> None:
        fields = allowed_metadata_fields(action)
        assert {"reason", "source", "job_id"} <= fields


class TestFiltering:
    def test_drops_everything_outside_the_allow_list(self) -> None:
        result = sanitize_metadata(
            AuditAction.CREDENTIAL_CREATED,
            {
                "provider": "openai",
                "label": "Prod",
                "secret": "sk-live-1234567890",
                "api_key": "sk-x",
                "password": "hunter2",
                "ciphertext": b"\x00",
            },
        )
        assert result == {"provider": "openai", "label": "Prod"}

    def test_an_action_with_no_entry_records_only_common_fields(self) -> None:
        result = sanitize_metadata(
            AuditAction.JOB_FAILED, {"task_name": "x", "reason": "y", "unexpected": "z"}
        )
        assert result == {"task_name": "x", "reason": "y"}

    def test_content_generation_records_the_model_never_the_prompt(self) -> None:
        opportunity = str(uuid4())
        result = sanitize_metadata(
            AuditAction.CONTENT_GENERATED,
            {
                "ai_model": "gpt-4o",
                "opportunity_id": opportunity,
                "prompt": "confidential client brief",
                "text": "the generated listing body",
            },
        )
        assert result == {"ai_model": "gpt-4o", "opportunity_id": opportunity}

    def test_empty_metadata_is_handled(self) -> None:
        assert sanitize_metadata(AuditAction.USER_LOGIN, None) == {}
        assert sanitize_metadata(AuditAction.USER_LOGIN, {}) == {}


class TestValueScrubbing:
    def test_a_permitted_field_carrying_a_token_is_still_scrubbed(self) -> None:
        # Second layer: the allow-list decides which fields exist, the scrubber
        # handles a permitted field whose *value* is secret-shaped.
        result = sanitize_metadata(
            AuditAction.USER_LOGIN_FAILED,
            {"email": "a@b.c", "failure": "rejected token Bearer abcdefghijkl"},
        )
        assert result["email"] == "a@b.c"
        assert REDACTED in result["failure"]

    def test_long_strings_are_truncated(self) -> None:
        result = sanitize_metadata(AuditAction.CAMPAIGN_UPDATED, {"changed_fields": "x" * 900})
        assert len(result["changed_fields"]) == 503
        assert result["changed_fields"].endswith("...")

    def test_long_lists_are_truncated(self) -> None:
        result = sanitize_metadata(
            AuditAction.MEMBER_ADDED, {"role_slugs": [f"r{i}" for i in range(80)]}
        )
        assert len(result["role_slugs"]) == 51
        assert result["role_slugs"][-1] == "..."

    def test_uuids_become_strings_for_jsonb(self) -> None:
        value = uuid4()
        assert sanitize_metadata(AuditAction.MEMBER_ADDED, {"user_id": value})["user_id"] == str(
            value
        )
