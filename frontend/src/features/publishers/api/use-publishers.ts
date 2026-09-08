"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { publishersApi } from "@/lib/api";
import { queryKeys } from "@/lib/query/keys";
import { useTenantId } from "@/lib/tenant/use-tenant";
import type {
  PublisherCreate,
  PublisherListParams,
  PublisherUpdate,
  QualificationRequest,
} from "@/types/api";

export function usePublishers(params: PublisherListParams) {
  const tenantId = useTenantId();

  return useQuery({
    queryKey: queryKeys.publishers.list(tenantId, params),
    queryFn: ({ signal }) => publishersApi.listPublishers(tenantId!, params, signal),
    enabled: Boolean(tenantId),
  });
}

export function usePublisher(publisherId: string | undefined) {
  const tenantId = useTenantId();

  return useQuery({
    queryKey: queryKeys.publishers.detail(tenantId, publisherId ?? ""),
    queryFn: () => publishersApi.getPublisher(tenantId!, publisherId!),
    enabled: Boolean(tenantId && publisherId),
  });
}

export function useCreatePublisher() {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: PublisherCreate) =>
      publishersApi.createPublisher(tenantId!, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.publishers.all(tenantId) });
    },
  });
}

export function useUpdatePublisher(publisherId: string) {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: PublisherUpdate) =>
      publishersApi.updatePublisher(tenantId!, publisherId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.publishers.all(tenantId) });
    },
  });
}

export function useDeletePublisher() {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (publisherId: string) =>
      publishersApi.deletePublisher(tenantId!, publisherId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.publishers.all(tenantId) });
    },
  });
}

/**
 * Qualify a publisher.
 *
 * Deliberately not optimistic (spec §55): the backend decides the outcome from
 * its own scoring, so guessing QUALIFIED here would show a status that may be
 * replaced a moment later by REJECTED.
 */
export function useQualifyPublisher(publisherId: string) {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: QualificationRequest = {}) =>
      publishersApi.qualifyPublisher(tenantId!, publisherId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.publishers.all(tenantId) });
      // Scores feed opportunity qualification, so those views may change too.
      await queryClient.invalidateQueries({
        queryKey: queryKeys.opportunities.all(tenantId),
      });
    },
  });
}
