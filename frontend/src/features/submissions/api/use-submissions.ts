"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { submissionsApi } from "@/lib/api";
import { queryKeys } from "@/lib/query/keys";
import { useTenantId } from "@/lib/tenant/use-tenant";
import type {
  SubmissionApproveRequest,
  SubmissionExecuteRequest,
  SubmissionListParams,
  SubmissionUpdate,
  SubmissionVerifyRequest,
} from "@/types/api";

export function useSubmissions(params: SubmissionListParams) {
  const tenantId = useTenantId();

  return useQuery({
    queryKey: queryKeys.submissions.list(tenantId, params),
    queryFn: ({ signal }) => submissionsApi.listSubmissions(tenantId!, params, signal),
    enabled: Boolean(tenantId),
  });
}

export function useSubmission(submissionId: string | undefined) {
  const tenantId = useTenantId();

  return useQuery({
    queryKey: queryKeys.submissions.detail(tenantId, submissionId ?? ""),
    queryFn: () => submissionsApi.getSubmission(tenantId!, submissionId!),
    enabled: Boolean(tenantId && submissionId),
  });
}

/**
 * The backend's submission state machine.
 *
 * Fetched rather than duplicated in the client, so the actions offered on a
 * submission always match what the backend will accept (spec §2).
 */
export function useSubmissionStateMachine() {
  const tenantId = useTenantId();

  return useQuery({
    queryKey: queryKeys.submissions.stateMachine(tenantId),
    queryFn: () => submissionsApi.getSubmissionStateMachine(tenantId!),
    enabled: Boolean(tenantId),
    // Effectively static for the life of a deployment.
    staleTime: 30 * 60_000,
  });
}

export function useReviewQueue() {
  const tenantId = useTenantId();

  return useQuery({
    queryKey: queryKeys.submissions.reviewQueue(tenantId),
    queryFn: () => submissionsApi.getReviewQueue(tenantId!, 10),
    enabled: Boolean(tenantId),
  });
}

/**
 * Invalidate everything a submission state change affects.
 *
 * A status change moves the row between tabs and updates the campaign funnel
 * and the dashboard counters, so all three are refreshed.
 */
function useSubmissionInvalidation() {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  return async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.submissions.all(tenantId) });
    await queryClient.invalidateQueries({ queryKey: queryKeys.campaigns.all(tenantId) });
    await queryClient.invalidateQueries({ queryKey: queryKeys.opportunities.all(tenantId) });
  };
}

export function useUpdateSubmission(submissionId: string) {
  const tenantId = useTenantId();
  const invalidate = useSubmissionInvalidation();

  return useMutation({
    mutationFn: (payload: SubmissionUpdate) =>
      submissionsApi.updateSubmission(tenantId!, submissionId, payload),
    onSuccess: invalidate,
  });
}

export function useSubmitForReview(submissionId: string) {
  const tenantId = useTenantId();
  const invalidate = useSubmissionInvalidation();

  return useMutation({
    mutationFn: () => submissionsApi.submitForReview(tenantId!, submissionId),
    onSuccess: invalidate,
  });
}

/**
 * Approve a submission.
 *
 * Never optimistic (spec §55): approval is the human-in-the-loop gate, and
 * showing it as approved before the backend agrees would misrepresent a
 * decision that carries an audit record.
 */
export function useApproveSubmission(submissionId: string) {
  const tenantId = useTenantId();
  const invalidate = useSubmissionInvalidation();

  return useMutation({
    mutationFn: (payload: SubmissionApproveRequest = {}) =>
      submissionsApi.approveSubmission(tenantId!, submissionId, payload),
    onSuccess: invalidate,
  });
}

/**
 * Record that the listing was submitted.
 *
 * For a manual workflow the user completes the publisher's own form in a new
 * tab and then marks it done here. Nothing attempts to automate a form behind
 * a CAPTCHA or anti-bot check (spec §29).
 */
export function useExecuteSubmission(submissionId: string) {
  const tenantId = useTenantId();
  const invalidate = useSubmissionInvalidation();

  return useMutation({
    mutationFn: (payload: SubmissionExecuteRequest) =>
      submissionsApi.executeSubmission(tenantId!, submissionId, payload),
    onSuccess: invalidate,
  });
}

export function useVerifySubmission(submissionId: string) {
  const tenantId = useTenantId();
  const invalidate = useSubmissionInvalidation();

  return useMutation({
    mutationFn: (payload: SubmissionVerifyRequest = { fetch_live: true }) =>
      submissionsApi.verifySubmission(tenantId!, submissionId, payload),
    onSuccess: invalidate,
  });
}

export function useRejectSubmission(submissionId: string) {
  const tenantId = useTenantId();
  const invalidate = useSubmissionInvalidation();

  return useMutation({
    mutationFn: (reason: string) =>
      submissionsApi.transitionSubmission(tenantId!, submissionId, {
        target_status: "REJECTED",
        reason,
      }),
    onSuccess: invalidate,
  });
}
