"""Master-key (KEK) providers.

The application never hardcodes key material. ``KeyProvider`` is the seam that
lets a cloud secret manager replace local env-var key handling without touching
a single call site: only the provider changes, and the ``key_version`` recorded
on each encrypted row tells the new provider which key to ask for.

This module deliberately depends on nothing but the standard library — the
wiring layer passes key bytes in, so ``app.core`` never imports ``app.config``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.config.settings import Settings

#: AES-256 master keys.
MASTER_KEY_BYTES = 32


@runtime_checkable
class KeyProvider(Protocol):
    """Supplies symmetric master keys by version."""

    @property
    def current_version(self) -> int:
        """Version that new ciphertexts should be wrapped with."""
        ...

    def get_key(self, version: int) -> bytes:
        """Return the 32-byte master key for ``version``.

        Raises:
            KeyError: the version is unknown to this provider.
        """
        ...


class EnvMasterKeyProvider:
    """Serves a single master key supplied by application configuration."""

    __slots__ = ("_key", "_version")

    def __init__(self, key: bytes, version: int) -> None:
        if len(key) != MASTER_KEY_BYTES:
            raise ValueError(f"master key must be exactly {MASTER_KEY_BYTES} bytes")
        if version < 1:
            raise ValueError("key version must be >= 1")
        self._key = key
        self._version = version

    @classmethod
    def from_settings(cls, settings: Settings) -> EnvMasterKeyProvider:
        """Build from validated settings (base64 length is checked there)."""
        return cls(settings.master_key, settings.encryption_key_version)

    @property
    def current_version(self) -> int:
        return self._version

    def get_key(self, version: int) -> bytes:
        if version != self._version:
            raise KeyError(
                f"master key version {version} is not available; "
                f"this deployment provides version {self._version}"
            )
        return self._key


class StaticKeyProvider:
    """In-memory, multi-version provider used by tests and key-rotation drills."""

    __slots__ = ("_keys", "_version")

    def __init__(self, keys: dict[int, bytes], current_version: int) -> None:
        for version, key in keys.items():
            if len(key) != MASTER_KEY_BYTES:
                raise ValueError(f"key version {version} must be {MASTER_KEY_BYTES} bytes")
        if current_version not in keys:
            raise ValueError("current_version must be present in keys")
        self._keys = dict(keys)
        self._version = current_version

    @property
    def current_version(self) -> int:
        return self._version

    def get_key(self, version: int) -> bytes:
        return self._keys[version]
