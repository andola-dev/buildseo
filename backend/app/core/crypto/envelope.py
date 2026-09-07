"""AES-256-GCM envelope encryption for tenant-supplied credentials.

Why envelope encryption rather than encrypting straight with the master key:

* Each credential gets its own random data encryption key (DEK), so one
  recovered ciphertext/DEK pair does not unlock every other tenant's secrets.
* Rotating the master key rewraps DEKs only — the secrets themselves are never
  decrypted or re-encrypted, so rotation needs no plaintext access.
* Additional authenticated data binds every ciphertext to the tenant, the
  credential row and the provider. A ciphertext copied into another row (or
  another tenant) fails authentication instead of decrypting.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.crypto.keys import KeyProvider
from app.core.exceptions import CredentialDecryptionError

NONCE_BYTES = 12  # GCM standard; never reused for a given key
DEK_BYTES = 32  # AES-256


@dataclass(frozen=True, slots=True)
class EncryptedPayload:
    """Everything needed to decrypt a secret, and nothing that reveals it."""

    ciphertext: bytes
    nonce: bytes
    encrypted_dek: bytes
    dek_nonce: bytes
    key_version: int

    def __repr__(self) -> str:
        """Redacted repr so an accidental log line cannot dump ciphertext."""
        return (
            f"EncryptedPayload(key_version={self.key_version}, "
            f"ciphertext=<{len(self.ciphertext)} bytes>)"
        )


def build_credential_aad(tenant_id: UUID, credential_id: UUID, provider: str) -> bytes:
    """Associated data binding a ciphertext to its row, tenant and provider."""
    return f"buildseo:credential:v1:{tenant_id}:{credential_id}:{provider.lower()}".encode()


class EnvelopeEncryptionService:
    """Encrypts and decrypts secrets using a per-secret DEK wrapped by a KEK."""

    __slots__ = ("_keys",)

    def __init__(self, key_provider: KeyProvider) -> None:
        self._keys = key_provider

    def encrypt(self, plaintext: str, *, aad: bytes) -> EncryptedPayload:
        """Encrypt ``plaintext`` under a fresh DEK wrapped with the current KEK."""
        if not plaintext:
            raise ValueError("cannot encrypt an empty secret")

        dek = os.urandom(DEK_BYTES)
        nonce = os.urandom(NONCE_BYTES)
        ciphertext = AESGCM(dek).encrypt(nonce, plaintext.encode("utf-8"), aad)

        version = self._keys.current_version
        dek_nonce = os.urandom(NONCE_BYTES)
        encrypted_dek = AESGCM(self._keys.get_key(version)).encrypt(dek_nonce, dek, aad)

        return EncryptedPayload(
            ciphertext=ciphertext,
            nonce=nonce,
            encrypted_dek=encrypted_dek,
            dek_nonce=dek_nonce,
            key_version=version,
        )

    def decrypt(self, payload: EncryptedPayload, *, aad: bytes) -> str:
        """Recover the plaintext secret.

        Raises:
            CredentialDecryptionError: wrong/rotated-away key, tampered
                ciphertext, or AAD that does not match the stored row. The
                message never distinguishes these cases to avoid an oracle.
        """
        try:
            kek = self._keys.get_key(payload.key_version)
        except KeyError as exc:
            raise CredentialDecryptionError(
                "Stored credential was encrypted with an unavailable key version",
                details={"key_version": payload.key_version},
            ) from exc

        try:
            dek = AESGCM(kek).decrypt(payload.dek_nonce, payload.encrypted_dek, aad)
            plaintext = AESGCM(dek).decrypt(payload.nonce, payload.ciphertext, aad)
        except InvalidTag as exc:
            raise CredentialDecryptionError() from exc
        return plaintext.decode("utf-8")

    def rewrap(self, payload: EncryptedPayload, *, aad: bytes) -> EncryptedPayload:
        """Re-wrap the DEK under the current KEK, leaving the secret untouched.

        This is the key-rotation path: the ciphertext bytes are reused verbatim,
        so no plaintext is produced beyond the DEK itself.
        """
        try:
            old_kek = self._keys.get_key(payload.key_version)
        except KeyError as exc:
            raise CredentialDecryptionError(
                "Cannot rewrap: source key version is unavailable",
                details={"key_version": payload.key_version},
            ) from exc

        try:
            dek = AESGCM(old_kek).decrypt(payload.dek_nonce, payload.encrypted_dek, aad)
        except InvalidTag as exc:
            raise CredentialDecryptionError() from exc

        version = self._keys.current_version
        dek_nonce = os.urandom(NONCE_BYTES)
        encrypted_dek = AESGCM(self._keys.get_key(version)).encrypt(dek_nonce, dek, aad)
        return EncryptedPayload(
            ciphertext=payload.ciphertext,
            nonce=payload.nonce,
            encrypted_dek=encrypted_dek,
            dek_nonce=dek_nonce,
            key_version=version,
        )
