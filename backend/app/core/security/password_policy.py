"""Password strength policy.

Kept free of any KDF dependency so Pydantic schemas can validate a password
without importing the hasher, and so the rules are unit-testable in isolation.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

DEFAULT_MIN_LENGTH = 12
DEFAULT_MAX_LENGTH = 128

_UPPER = re.compile(r"[A-Z]")
_LOWER = re.compile(r"[a-z]")
_DIGIT = re.compile(r"[0-9]")
_SYMBOL = re.compile(r"[^A-Za-z0-9]")
_SEQUENTIAL = re.compile(
    r"(?:abcdef|bcdefg|cdefgh|qwerty|asdfgh|zxcvbn|123456|234567|345678|456789|987654)",
)

#: Small, high-signal deny list. A production deployment should point the
#: policy at a full breached-password corpus (e.g. HIBP k-anonymity range API);
#: ``extra_denylist`` exists for exactly that.
_COMMON_PASSWORDS = frozenset(
    {
        "password",
        "password1",
        "password123",
        "passw0rd",
        "p@ssw0rd",
        "p@ssword",
        "administrator",
        "letmein",
        "welcome",
        "welcome1",
        "iloveyou",
        "monkey",
        "dragon",
        "sunshine",
        "princess",
        "football",
        "baseball",
        "qwerty",
        "qwerty123",
        "1q2w3e4r",
        "abc123",
        "123456",
        "1234567",
        "12345678",
        "123456789",
        "1234567890",
        "qwertyuiop",
        "trustno1",
        "changeme",
        "secret",
        "master",
        "starwars",
        "superman",
        "batman",
        "buildseo",
        "buildseo123",
        "admin",
        "admin123",
        "root",
        "toor",
        "test",
        "test123",
    }
)


@dataclass(frozen=True, slots=True)
class PasswordPolicy:
    """Configurable complexity rules."""

    min_length: int = DEFAULT_MIN_LENGTH
    max_length: int = DEFAULT_MAX_LENGTH
    require_uppercase: bool = True
    require_lowercase: bool = True
    require_digit: bool = True
    require_symbol: bool = True
    forbid_common: bool = True
    #: Reject passwords derived from the user's own identifiers.
    forbid_personal_data: bool = True
    #: Guards against low-entropy padding such as ``Aa1!aaaaaaaaaa``.
    min_distinct_characters: int = 5
    max_single_character_ratio: float = 0.5
    extra_denylist: frozenset[str] = field(default_factory=frozenset)

    def violations(self, password: str, *, personal_data: tuple[str, ...] = ()) -> list[str]:
        """Return every reason ``password`` is unacceptable (empty list = OK).

        All rules are evaluated so the caller can show a complete list instead
        of making the user discover requirements one submission at a time.
        """
        problems: list[str] = []
        if password != unicodedata.normalize("NFKC", password):
            password = unicodedata.normalize("NFKC", password)

        if len(password) < self.min_length:
            problems.append(f"must be at least {self.min_length} characters long")
        if len(password) > self.max_length:
            problems.append(f"must be at most {self.max_length} characters long")
        if self.require_uppercase and not _UPPER.search(password):
            problems.append("must contain an uppercase letter")
        if self.require_lowercase and not _LOWER.search(password):
            problems.append("must contain a lowercase letter")
        if self.require_digit and not _DIGIT.search(password):
            problems.append("must contain a digit")
        if self.require_symbol and not _SYMBOL.search(password):
            problems.append("must contain a symbol")
        if password.strip() != password:
            problems.append("must not begin or end with whitespace")

        folded = password.casefold()
        if self.forbid_common:
            stripped = re.sub(r"[^a-z0-9]", "", folded)
            if folded in _COMMON_PASSWORDS or stripped in _COMMON_PASSWORDS:
                problems.append("is too common")
            elif _SEQUENTIAL.search(folded):
                problems.append("must not contain a keyboard or numeric sequence")
        if self.extra_denylist and folded in self.extra_denylist:
            problems.append("is not allowed")

        if password:
            if len(set(password)) < self.min_distinct_characters:
                problems.append(
                    f"must contain at least {self.min_distinct_characters} different characters"
                )
            most_common = Counter(password).most_common(1)[0][1]
            if most_common > len(password) * self.max_single_character_ratio:
                problems.append("must not repeat one character through most of the password")

        if self.forbid_personal_data:
            for item in personal_data:
                token = (item or "").split("@")[0].casefold()
                if len(token) >= 4 and token in folded:
                    problems.append("must not contain your name or email address")
                    break

        return problems

    def is_acceptable(self, password: str, *, personal_data: tuple[str, ...] = ()) -> bool:
        return not self.violations(password, personal_data=personal_data)


DEFAULT_POLICY = PasswordPolicy()
