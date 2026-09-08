/**
 * Submissions — the human-reviewed listing workflow and link verification.
 *
 * Every state change is a backend call: the frontend never computes whether a
 * transition is allowed, it asks (spec §2/§29).
 */

import { api } from "@/lib/api/http";
import { unwrap, unwrapAck, unwrapPage, type Page } from "@/lib/api/envelope";
import type {
  ApiEnvelope,
  JobAccepted,
  PaginatedEnvelope,
  Submission,
  SubmissionApproveRequest,
  SubmissionCreate,
  SubmissionExecuteRequest,
  SubmissionListParams,
  SubmissionStateMachine,
  SubmissionTransitionRequest,
  SubmissionUpdate,
  SubmissionVerifyRequest,
  UUID,
} from "@/types/api";

const BASE = "/submissions";

export async function listSubmissions(
  tenantId: string,
  params?: SubmissionListParams,
  signal?: AbortSignal,
): Promise<Page<Submission>> {
  return unwrapPage(
    await api.get<PaginatedEnvelope<Submission>>(BASE, {
      query: { ...params },
      tenantId,
      ...(signal ? { signal } : {}),
    }),
  );
}

export async function getSubmission(
  tenantId: string,
  submissionId: UUID,
): Promise<Submission> {
  return unwrap(
    await api.get<ApiEnvelope<Submission>>(`${BASE}/${submissionId}`, { tenantId }),
  );
}

/** Prepare a submission from an approved opportunity. */
export async function createSubmission(
  tenantId: string,
  payload: SubmissionCreate,
): Promise<Submission> {
  return unwrap(await api.post<ApiEnvelope<Submission>>(BASE, payload, { tenantId }));
}

export async function updateSubmission(
  tenantId: string,
  submissionId: UUID,
  payload: SubmissionUpdate,
): Promise<Submission> {
  return unwrap(
    await api.patch<ApiEnvelope<Submission>>(`${BASE}/${submissionId}`, payload, {
      tenantId,
    }),
  );
}

export async function deleteSubmission(
  tenantId: string,
  submissionId: UUID,
): Promise<void> {
  unwrapAck(await api.del<ApiEnvelope<unknown>>(`${BASE}/${submissionId}`, { tenantId }));
}

export async function submitForReview(
  tenantId: string,
  submissionId: UUID,
): Promise<Submission> {
  return unwrap(
    await api.post<ApiEnvelope<Submission>>(
      `${BASE}/${submissionId}/submit-for-review`,
      undefined,
      { tenantId },
    ),
  );
}

export async function approveSubmission(
  tenantId: string,
  submissionId: UUID,
  payload: SubmissionApproveRequest = {},
): Promise<Submission> {
  return unwrap(
    await api.post<ApiEnvelope<Submission>>(`${BASE}/${submissionId}/approve`, payload, {
      tenantId,
    }),
  );
}

/**
 * Record that the listing was actually submitted.
 *
 * For a manual workflow the user opens the publisher's submission page in a new
 * tab, completes the form themselves, then comes back and marks it done — this
 * is that call. Nothing here attempts to defeat a CAPTCHA or anti-bot check
 * (spec §29).
 */
export async function executeSubmission(
  tenantId: string,
  submissionId: UUID,
  payload: SubmissionExecuteRequest = {},
): Promise<Submission> {
  return unwrap(
    await api.post<ApiEnvelope<Submission>>(`${BASE}/${submissionId}/execute`, payload, {
      tenantId,
    }),
  );
}

/** Check the live page for the link. */
export async function verifySubmission(
  tenantId: string,
  submissionId: UUID,
  payload: SubmissionVerifyRequest = {},
): Promise<Submission> {
  return unwrap(
    await api.post<ApiEnvelope<Submission>>(`${BASE}/${submissionId}/verify`, payload, {
      tenantId,
      timeoutMs: 60_000,
    }),
  );
}

/** Queue verification as a background job when a live fetch is expected to be slow. */
export async function verifySubmissionAsync(
  tenantId: string,
  submissionId: UUID,
  payload: SubmissionVerifyRequest = {},
): Promise<JobAccepted> {
  return unwrap(
    await api.post<ApiEnvelope<JobAccepted>>(
      `${BASE}/${submissionId}/verify-async`,
      payload,
      { tenantId },
    ),
  );
}

export async function transitionSubmission(
  tenantId: string,
  submissionId: UUID,
  payload: SubmissionTransitionRequest,
): Promise<Submission> {
  return unwrap(
    await api.post<ApiEnvelope<Submission>>(
      `${BASE}/${submissionId}/transition`,
      payload,
      { tenantId },
    ),
  );
}

/**
 * The submission state machine.
 *
 * Fetched rather than duplicated so the actions offered on a submission always
 * match what the backend will accept.
 */
export async function getSubmissionStateMachine(
  tenantId: string,
): Promise<SubmissionStateMachine> {
  return unwrap(
    await api.get<ApiEnvelope<SubmissionStateMachine>>(`${BASE}/state-machine`, {
      tenantId,
    }),
  );
}

/** Submissions currently awaiting a reviewer. */
export async function getReviewQueue(
  tenantId: string,
  limit = 50,
): Promise<Submission[]> {
  return unwrap(
    await api.get<ApiEnvelope<Submission[]>>(`${BASE}/review-queue`, {
      query: { limit },
      tenantId,
    }),
  );
}
