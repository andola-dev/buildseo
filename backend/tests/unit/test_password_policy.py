"""Password strength policy."""

from __future__ import annotations

import pytest

from app.core.security.password_policy import DEFAULT_POLICY, PasswordPolicy

pytestmark = pytest.mark.unit


class TestAcceptablePasswords:
    @pytest.mark.parametrize(
        "password", ["Corr3ct!HorseBattery", "Tr0ub4dor&3xyz", "M0nsoon#Rain2026"]
    )
    def test_accepts_a_strong_password(self, password: str) -> None:
        assert DEFAULT_POLICY.is_acceptable(password), DEFAULT_POLICY.violations(password)


class TestRejections:
    @pytest.mark.parametrize(
        ("password", "expected_reason"),
        [
            ("Ab3!x", "at least 12"),
            ("alllowercase1!", "uppercase"),
            ("ALLUPPERCASE1!", "lowercase"),
            ("NoDigitsHere!!", "digit"),
            ("NoSymbols1234a", "symbol"),
            ("Password123!", "too common"),
            ("Aa1!aaaaaaaaaa", "repeat one character"),
            ("Abcdef123456!X", "sequence"),
            ("Aa1!Aa1!Aa1!", "different characters"),
            ("Corr3ct!Horse  ", "whitespace"),
        ],
    )
    def test_explains_why_a_password_is_rejected(self, password: str, expected_reason: str) -> None:
        violations = DEFAULT_POLICY.violations(password)
        assert any(expected_reason in reason for reason in violations), violations

    def test_reports_every_violation_at_once(self) -> None:
        # A user should not have to discover the rules one submission at a time.
        assert len(DEFAULT_POLICY.violations("abc")) >= 4

    def test_rejects_an_over_long_password(self) -> None:
        violations = DEFAULT_POLICY.violations("Aa1!" + "xyzQ7#" * 40)
        assert any("at most" in reason for reason in violations)


class TestPersonalData:
    def test_rejects_a_password_derived_from_the_users_own_email(self) -> None:
        violations = DEFAULT_POLICY.violations(
            "Anurag2026!Secure", personal_data=("anurag.pattnaik@example.com", "Anurag")
        )
        assert any("your name or email" in reason for reason in violations)

    def test_the_same_password_is_fine_for_a_different_person(self) -> None:
        assert DEFAULT_POLICY.is_acceptable("Anurag2026!Secure")

    def test_ignores_a_personal_token_too_short_to_matter(self) -> None:
        # A two-letter name would otherwise reject almost everything.
        assert DEFAULT_POLICY.is_acceptable("Corr3ct!HorseBattery", personal_data=("Al",))


class TestConfigurability:
    def test_rules_can_be_relaxed(self) -> None:
        lax = PasswordPolicy(min_length=8, require_symbol=False, forbid_common=False)
        assert lax.is_acceptable("Passw0rdy")

    def test_an_extra_denylist_is_honoured(self) -> None:
        policy = PasswordPolicy(extra_denylist=frozenset({"tenantsecret1!"}))
        assert not policy.is_acceptable("TenantSecret1!")

    def test_distinct_character_floor_is_configurable(self) -> None:
        assert PasswordPolicy(min_distinct_characters=2).is_acceptable("Aa1!Aa1!Aa1!")
