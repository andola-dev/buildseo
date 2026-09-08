"""Envelope encryption for BYOK credentials.

The properties tested here are the ones the whole BYOK design rests on:
a ciphertext is useless without the master key, it is bound to the exact row
and tenant it was created for, tampering is detected, and rotating the master
key never requires touching the secrets themselves.
"""

from __future__ import annotations

import dataclasses
import os
from uuid import uuid4

import pytest

from app.core.crypto.envelope import (
    DEK_BYTES,
    NONCE_BYTES,
    EnvelopeEncryptionService,
    build_credential_aad,
)
from app.core.crypto.keys import EnvMasterKeyProvider, KeyProvider, StaticKeyProvider
from app.core.exceptions import CredentialDecryptionError

pytestmark = pytest.mark.unit

SECRET = "sk-proj-abc123456789xyz"


@pytest.fixture
def keys() -> tuple[bytes, bytes]:
    return os.urandom(32), os.urandom(32)


@pytest.fixture
def service(keys: tuple[bytes, bytes]) -> EnvelopeEncryptionService:
    return EnvelopeEncryptionService(StaticKeyProvider({1: keys[0]}, 1))


@pytest.fixture
def aad() -> bytes:
    return build_credential_aad(uuid4(), uuid4(), "openai")


class TestKeyProviders:
    def test_providers_satisfy_the_protocol(self, keys: tuple[bytes, bytes]) -> None:
        assert isinstance(StaticKeyProvider({1: keys[0]}, 1), KeyProvider)
        assert isinstance(EnvMasterKeyProvider(keys[0], 1), KeyProvider)

    def test_rejects_a_wrong_length_master_key(self) -> None:
        with pytest.raises(ValueError, match="32 bytes"):
            EnvMasterKeyProvider(b"tooshort", 1)

    def test_rejects_a_current_version_it_does_not_hold(self, keys: tuple[bytes, bytes]) -> None:
        with pytest.raises(ValueError, match="current_version"):
            StaticKeyProvider({1: keys[0]}, 2)

    def test_env_provider_serves_only_its_own_version(self, keys: tuple[bytes, bytes]) -> None:
        provider = EnvMasterKeyProvider(keys[0], 3)
        assert provider.get_key(3) == keys[0]
        with pytest.raises(KeyError):
            provider.get_key(1)


class TestRoundTrip:
    def test_encrypt_then_decrypt_returns_the_secret(
        self, service: EnvelopeEncryptionService, aad: bytes
    ) -> None:
        assert service.decrypt(service.encrypt(SECRET, aad=aad), aad=aad) == SECRET

    def test_the_secret_never_appears_in_the_stored_bytes(
        self, service: EnvelopeEncryptionService, aad: bytes
    ) -> None:
        payload = service.encrypt(SECRET, aad=aad)
        raw = SECRET.encode()
        assert raw not in payload.ciphertext
        assert raw not in payload.encrypted_dek

    def test_each_encryption_uses_a_fresh_key_and_nonce(
        self, service: EnvelopeEncryptionService, aad: bytes
    ) -> None:
        first = service.encrypt(SECRET, aad=aad)
        second = service.encrypt(SECRET, aad=aad)
        assert first.ciphertext != second.ciphertext
        assert first.nonce != second.nonce
        assert first.encrypted_dek != second.encrypted_dek

    def test_nonce_sizes_match_the_database_constraints(
        self, service: EnvelopeEncryptionService, aad: bytes
    ) -> None:
        payload = service.encrypt(SECRET, aad=aad)
        assert len(payload.nonce) == NONCE_BYTES == 12
        assert len(payload.dek_nonce) == NONCE_BYTES
        # The wrapped DEK is the key plus a GCM tag.
        assert len(payload.encrypted_dek) == DEK_BYTES + 16

    def test_refuses_to_encrypt_nothing(
        self, service: EnvelopeEncryptionService, aad: bytes
    ) -> None:
        with pytest.raises(ValueError):
            service.encrypt("", aad=aad)

    def test_payload_repr_is_redacted(self, service: EnvelopeEncryptionService, aad: bytes) -> None:
        text = repr(service.encrypt(SECRET, aad=aad))
        assert "ciphertext=<" in text
        assert SECRET not in text


class TestAadBinding:
    """A ciphertext must be worthless outside the row it was created for."""

    def test_aad_is_case_insensitive_in_the_provider(self) -> None:
        tenant, credential = uuid4(), uuid4()
        assert build_credential_aad(tenant, credential, "OpenAI") == build_credential_aad(
            tenant, credential, "openai"
        )

    @pytest.mark.parametrize("changed", ["tenant", "credential", "provider"])
    def test_a_ciphertext_moved_to_another_row_or_tenant_fails(
        self, service: EnvelopeEncryptionService, changed: str
    ) -> None:
        tenant, credential = uuid4(), uuid4()
        payload = service.encrypt(SECRET, aad=build_credential_aad(tenant, credential, "openai"))
        wrong = build_credential_aad(
            uuid4() if changed == "tenant" else tenant,
            uuid4() if changed == "credential" else credential,
            "anthropic" if changed == "provider" else "openai",
        )
        with pytest.raises(CredentialDecryptionError):
            service.decrypt(payload, aad=wrong)


class TestTamperDetection:
    @pytest.mark.parametrize("field", ["ciphertext", "encrypted_dek", "nonce", "dek_nonce"])
    def test_flipping_a_single_bit_is_detected(
        self, service: EnvelopeEncryptionService, aad: bytes, field: str
    ) -> None:
        payload = service.encrypt(SECRET, aad=aad)
        original = getattr(payload, field)
        tampered = dataclasses.replace(
            payload, **{field: original[:-1] + bytes([original[-1] ^ 1])}
        )
        with pytest.raises(CredentialDecryptionError):
            service.decrypt(tampered, aad=aad)


class TestWrongKey:
    def test_a_different_master_key_cannot_decrypt(
        self, service: EnvelopeEncryptionService, aad: bytes, keys: tuple[bytes, bytes]
    ) -> None:
        payload = service.encrypt(SECRET, aad=aad)
        other = EnvelopeEncryptionService(StaticKeyProvider({1: keys[1]}, 1))
        with pytest.raises(CredentialDecryptionError):
            other.decrypt(payload, aad=aad)

    def test_an_unavailable_key_version_fails_clearly(
        self, service: EnvelopeEncryptionService, aad: bytes, keys: tuple[bytes, bytes]
    ) -> None:
        payload = service.encrypt(SECRET, aad=aad)
        rotated_away = EnvelopeEncryptionService(StaticKeyProvider({2: keys[1]}, 2))
        with pytest.raises(CredentialDecryptionError):
            rotated_away.decrypt(payload, aad=aad)


class TestKeyRotation:
    def test_rewrap_changes_the_key_version_without_touching_the_secret(
        self, service: EnvelopeEncryptionService, aad: bytes, keys: tuple[bytes, bytes]
    ) -> None:
        payload = service.encrypt(SECRET, aad=aad)
        rotator = EnvelopeEncryptionService(StaticKeyProvider({1: keys[0], 2: keys[1]}, 2))

        rewrapped = rotator.rewrap(payload, aad=aad)

        assert rewrapped.key_version == 2
        # The point of envelope encryption: the secret's ciphertext is reused
        # verbatim, so rotation never decrypts a secret.
        assert rewrapped.ciphertext == payload.ciphertext
        assert rewrapped.nonce == payload.nonce
        assert rewrapped.encrypted_dek != payload.encrypted_dek

    def test_a_rewrapped_payload_opens_with_only_the_new_key(
        self, service: EnvelopeEncryptionService, aad: bytes, keys: tuple[bytes, bytes]
    ) -> None:
        payload = service.encrypt(SECRET, aad=aad)
        rotator = EnvelopeEncryptionService(StaticKeyProvider({1: keys[0], 2: keys[1]}, 2))
        rewrapped = rotator.rewrap(payload, aad=aad)

        new_key_only = EnvelopeEncryptionService(StaticKeyProvider({2: keys[1]}, 2))
        assert new_key_only.decrypt(rewrapped, aad=aad) == SECRET

    def test_rewrap_refuses_when_the_source_key_is_gone(
        self, service: EnvelopeEncryptionService, aad: bytes, keys: tuple[bytes, bytes]
    ) -> None:
        payload = service.encrypt(SECRET, aad=aad)
        without_v1 = EnvelopeEncryptionService(StaticKeyProvider({2: keys[1]}, 2))
        with pytest.raises(CredentialDecryptionError):
            without_v1.rewrap(payload, aad=aad)
