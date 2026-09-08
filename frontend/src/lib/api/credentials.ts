/**
 * Bring-your-own-key provider credentials.
 *
 * The secret is write-only: it appears in `CredentialCreate.secret` and
 * `CredentialUpdate.secret` and in no read model. `CredentialRead` carries only
 * `masked_key`, so there is no code path — here or anywhere else in the
 * frontend — that could receive a decrypted key (spec §32).
 *
 * Deleting a credential calls the backend, which destroys the encrypted
 * material. Removing it from client state alone would be meaningless (spec §67).
 */

import { api } from "@/lib/api/http";
import { unwrap, unwrapAck, unwrapPage, type Page } from "@/lib/api/envelope";
import type {
  ApiEnvelope,
  Credential,
  CredentialCreate,
  CredentialListParams,
  CredentialUpdate,
  CredentialVerifyResult,
  PaginatedEnvelope,
  UUID,
} from "@/types/api";

const BASE = "/credentials";

export async function listCredentials(
  tenantId: string,
  params?: CredentialListParams,
): Promise<Page<Credential>> {
  return unwrapPage(
    await api.get<PaginatedEnvelope<Credential>>(BASE, { query: { ...params }, tenantId }),
  );
}

export async function getCredential(
  tenantId: string,
  credentialId: UUID,
): Promise<Credential> {
  return unwrap(
    await api.get<ApiEnvelope<Credential>>(`${BASE}/${credentialId}`, { tenantId }),
  );
}

/**
 * Store a new credential.
 *
 * The caller must not retain `payload.secret` after this resolves; the forms in
 * `features/credentials` reset their secret field on success.
 */
export async function createCredential(
  tenantId: string,
  payload: CredentialCreate,
): Promise<Credential> {
  return unwrap(await api.post<ApiEnvelope<Credential>>(BASE, payload, { tenantId }));
}

export async function updateCredential(
  tenantId: string,
  credentialId: UUID,
  payload: CredentialUpdate,
): Promise<Credential> {
  return unwrap(
    await api.patch<ApiEnvelope<Credential>>(`${BASE}/${credentialId}`, payload, {
      tenantId,
    }),
  );
}

export async function deleteCredential(
  tenantId: string,
  credentialId: UUID,
): Promise<void> {
  unwrapAck(await api.del<ApiEnvelope<unknown>>(`${BASE}/${credentialId}`, { tenantId }));
}

/** Ask the backend to call the provider and report whether the key works. */
export async function verifyCredential(
  tenantId: string,
  credentialId: UUID,
): Promise<CredentialVerifyResult> {
  return unwrap(
    await api.post<ApiEnvelope<CredentialVerifyResult>>(
      `${BASE}/${credentialId}/verify`,
      undefined,
      { tenantId, timeoutMs: 45_000 },
    ),
  );
}
