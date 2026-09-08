"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { opportunitiesApi } from "@/lib/api";
import { queryKeys } from "@/lib/query/keys";
import { useTenantId } from "@/lib/tenant/use-tenant";
import type {
  ContentGenerationRequest,
  ContentReviewRequest,
  OpportunityListParams,
  OpportunityUpdate,
} from "@/types/api";

export function useOpportunities(params: OpportunityListParams) {
  const tenantId = useTenantId();

  return useQuery({
    queryKey: queryKeys.opportunities.list(tenantId, params),
    queryFn: ({ signal }) => opportunitiesApi.listOpportunities(tenantId!, params, signal),
    enabled: Boolean(tenantId),
  });
}

export function useOpportunity(opportunityId: string | undefined) {
  const tenantId = useTenantId();

  return useQuery({
    queryKey: queryKeys.opportunities.detail(tenantId, opportunityId ?? ""),
    queryFn: () => opportunitiesApi.getOpportunity(tenantId!, opportunityId!),
    enabled: Boolean(tenantId && opportunityId),
  });
}

/**
 * Invalidate everything an opportunity state change can affect.
 *
 * Selecting or rejecting moves the row between filtered views and changes the
 * campaign funnel, so refreshing only the detail entry would leave stale lists
 * behind.
 */
function useOpportunityInvalidation() {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  return async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.opportunities.all(tenantId) });
    await queryClient.invalidateQueries({ queryKey: queryKeys.campaigns.all(tenantId) });
  };
}

export function useUpdateOpportunity(opportunityId: string) {
  const tenantId = useTenantId();
  const invalidate = useOpportunityInvalidation();

  return useMutation({
    mutationFn: (payload: OpportunityUpdate) =>
      opportunitiesApi.updateOpportunity(tenantId!, opportunityId, payload),
    onSuccess: invalidate,
  });
}

/**
 * Approve (select) an opportunity.
 *
 * Not optimistic (spec §55): the backend validates the transition against its
 * state machine and may refuse, so showing SELECTED before it confirms would
 * be a lie the UI then has to take back.
 */
export function useSelectOpportunity(opportunityId: string) {
  const tenantId = useTenantId();
  const invalidate = useOpportunityInvalidation();

  return useMutation({
    mutationFn: () => opportunitiesApi.selectOpportunity(tenantId!, opportunityId),
    onSuccess: invalidate,
  });
}

export function useRejectOpportunity(opportunityId: string) {
  const tenantId = useTenantId();
  const invalidate = useOpportunityInvalidation();

  return useMutation({
    mutationFn: (reason: string) =>
      opportunitiesApi.rejectOpportunity(tenantId!, opportunityId, { reason }),
    onSuccess: invalidate,
  });
}

export function useQualifyOpportunity(opportunityId: string) {
  const tenantId = useTenantId();
  const invalidate = useOpportunityInvalidation();

  return useMutation({
    mutationFn: () =>
      opportunitiesApi.qualifyOpportunity(tenantId!, opportunityId, { fetch_live: false }),
    onSuccess: invalidate,
  });
}

/* -------------------------------------------------------------------------- */
/* AI-generated listing content                                               */
/* -------------------------------------------------------------------------- */

export function useGeneratedContent(opportunityId: string | undefined) {
  const tenantId = useTenantId();

  return useQuery({
    queryKey: queryKeys.opportunities.content(tenantId, opportunityId ?? ""),
    queryFn: () => opportunitiesApi.listGeneratedContent(tenantId!, opportunityId!),
    enabled: Boolean(tenantId && opportunityId),
  });
}

/**
 * Ask the backend to generate listing content.
 *
 * The request carries no provider credentials: the backend uses the
 * workspace's stored BYOK key, so no API key is ever present in the browser
 * (spec §27/§48).
 */
export function useGenerateContent(opportunityId: string) {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: ContentGenerationRequest = {}) =>
      opportunitiesApi.generateContent(tenantId!, opportunityId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.opportunities.content(tenantId, opportunityId),
      });
    },
  });
}

/** Accept, reject or accept-with-edits a generated draft. */
export function useReviewContent(opportunityId: string) {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      contentId,
      payload,
    }: {
      contentId: string;
      payload: ContentReviewRequest;
    }) => opportunitiesApi.reviewContent(tenantId!, opportunityId, contentId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.opportunities.content(tenantId, opportunityId),
      });
      await queryClient.invalidateQueries({
        queryKey: queryKeys.opportunities.detail(tenantId, opportunityId),
      });
    },
  });
}
