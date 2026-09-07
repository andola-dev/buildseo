"""Argon2id password hashing.

Argon2id is the OWASP-recommended default: it combines Argon2i's side-channel
resistance with Argon2d's GPU-cracking resistance, and its memory cost makes
custom-hardware attacks expensive in a way bcrypt's fixed 4 KiB cannot.

The hash string produced by argon2-cffi embeds the algorithm, version, cost
parameters and salt, so raising the cost parameters later does not invalidate
existing hashes — :meth:`PasswordHasher.needs_rehash` detects stale ones and the
login path transparently upgrades them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from argon2 import PasswordHasher as Argon2PasswordHasher
from argon2 import Type as Argon2Type
from argon2.exceptions import HashingError, InvalidHashError, VerificationError, VerifyMismatchError

from app.core.exceptions import ValidationError
from app.core.security.password_policy import PasswordPolicy

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.config.settings import Settings

#: Hash of a throwaway password, used to equalise timing when an email is
#: unknown so login cannot be turned into a user-enumeration oracle.
_DUMMY_PASSWORD = "buildseo-dummy-verification-target"  # noqa: S105 - not a credential


class PasswordHasher:
    """Hashes and verifies passwords, and enforces the strength policy."""

    __slots__ = ("_dummy_hash", "_hasher", "_policy")

    def __init__(
        self,
        *,
        time_cost: int = 3,
        memory_cost_kib: int = 65_536,
        parallelism: int = 4,
        hash_length: int = 32,
        policy: PasswordPolicy | None = None,
    ) -> None:
        self._hasher = Argon2PasswordHasher(
            time_cost=time_cost,
            memory_cost=memory_cost_kib,
            parallelism=parallelism,
            hash_len=hash_length,
            type=Argon2Type.ID,
        )
        self._policy = policy or PasswordPolicy()
        self._dummy_hash = self._hasher.hash(_DUMMY_PASSWORD)

    @classmethod
    def from_settings(cls, settings: Settings) -> PasswordHasher:
        return cls(
            time_cost=settings.argon2_time_cost,
            memory_cost_kib=settings.argon2_memory_cost_kib,
            parallelism=settings.argon2_parallelism,
            hash_length=settings.argon2_hash_length,
            policy=PasswordPolicy(
                min_length=settings.password_min_length,
                max_length=settings.password_max_length,
            ),
        )

    @property
    def policy(self) -> PasswordPolicy:
        return self._policy

    def validate_strength(self, password: str, *, personal_data: tuple[str, ...] = ()) -> None:
        """Raise :class:`ValidationError` listing every policy violation."""
        problems = self._policy.violations(password, personal_data=personal_data)
        if problems:
            raise ValidationError(
                "Password does not meet the security policy",
                code="WEAK_PASSWORD",
                details={"requirements": problems},
            )

    def hash(self, password: str) -> str:
        """Hash a password. Strength must already have been validated."""
        try:
            return self._hasher.hash(password)
        except HashingError as exc:  # pragma: no cover - argon2 internal failure
            raise ValidationError("Password could not be processed") from exc

    def verify(self, password: str, password_hash: str) -> bool:
        """Return whether ``password`` matches ``password_hash``.

        Returns ``False`` instead of raising for every mismatch case, including
        a malformed stored hash, so callers cannot accidentally distinguish
        "wrong password" from "corrupt row" in an API response.
        """
        try:
            return self._hasher.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        """True when the stored hash predates the current cost parameters."""
        try:
            return self._hasher.check_needs_rehash(password_hash)
        except InvalidHashError:  # pragma: no cover - corrupt stored hash
            return True

    def dummy_verify(self) -> None:
        """Spend the same work as a real verification, for unknown emails.

        Without this, "unknown email" would return measurably faster than
        "wrong password" and leak which addresses are registered.
        """
        try:
            self._hasher.verify(self._dummy_hash, "not-the-dummy-password")
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return
