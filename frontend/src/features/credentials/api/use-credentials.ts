"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { aiApi, credentialsApi } from "@/lib/api";
import { queryKeys } from "@/lib/query/keys";
import { useTenantId } from "@/lib/tenant/use-tenant";
import type {
  AiConfigUpsert,
  CredentialCreate,
  CredentialListParams,
  CredentialUpdate,
} from "@/types/api";

/**
 * BYOK credentials.
 *
 * The read model carries only `masked_key`, so nothing in this cache ever holds
 * a usable secret. The plaintext key exists only in the submitting form's local
 * state, and only until the request resolves (spec §32).
 */
export function useCredentials(params: CredentialListParams = {}) {
  const tenantId = useTenantId();

  return useQuery({
    queryKey: queryKeys.credentials.list(tenantId, params),
    queryFn: () => credentialsApi.listCredentials(tenantId!, { page_size: 100, ...params }),
    enabled: Boolean(tenantId),
  });
}

export function useCreateCredential() {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: CredentialCreate) =>
      credentialsApi.createCredential(tenantId!, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.credentials.all(tenantId) });
      // A newly configured key can make a discovery provider available.
      await queryClient.invalidateQueries({ queryKey: queryKeys.publishers.all(tenantId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.ai.all(tenantId) });
    },
  });
}

export function useUpdateCredential() {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      credentialId,
      payload,
    }: {
      credentialId: string;
      payload: CredentialUpdate;
    }) => credentialsApi.updateCredential(tenantId!, credentialId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.credentials.all(tenantId) });
    },
  });
}

/**
 * Delete a credential.
 *
 * The backend destroys the encrypted material; the cache is then invalidated so
 * the row disappears. Removing it from client state alone would leave the key
 * live on the server (spec §67).
 */
export function useDeleteCredential() {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (credentialId: string) =>
      credentialsApi.deleteCredential(tenantId!, credentialId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.credentials.all(tenantId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.ai.all(tenantId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.publishers.all(tenantId) });
    },
  });
}

/** Ask the backend to call the provider and report whether the key works. */
export function useVerifyCredential() {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (credentialId: string) =>
      credentialsApi.verifyCredential(tenantId!, credentialId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.credentials.all(tenantId) });
    },
  });
}

/* -------------------------------------------------------------------------- */
/* AI configuration                                                           */
/* -------------------------------------------------------------------------- */

export function useAiConfigs() {
  const tenantId = useTenantId();

  return useQuery({
    queryKey: queryKeys.ai.configs(tenantId),
    queryFn: () => aiApi.listAiConfigs(tenantId!),
    enabled: Boolean(tenantId),
  });
}

export function useUpsertAiConfig() {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: AiConfigUpsert) => aiApi.upsertAiConfig(tenantId!, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.ai.configs(tenantId) });
    },
  });
}

export function useDeleteAiConfig() {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (configId: string) => aiApi.deleteAiConfig(tenantId!, configId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.ai.configs(tenantId) });
    },
  });
}
