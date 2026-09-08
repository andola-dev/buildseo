/**
 * Opportunities — a campaign paired with a publisher — and their AI content.
 *
 * Content generation happens server-side: the browser asks the backend to
 * generate, and the backend uses the workspace's stored BYOK credential. No
 * provider key ever reaches the client (spec §27).
 */

import { api } from "@/lib/api/http";
import { unwrap, unwrapAck, unwrapPage, type Page } from "@/lib/api/envelope";
import type {
  ApiEnvelope,
  ContentGenerationRequest,
  ContentReviewRequest,
  GeneratedContent,
  Opportunity,
  OpportunityCreate,
  OpportunityListParams,
  OpportunityRejectRequest,
  OpportunityTransitionRequest,
  OpportunityUpdate,
  PaginatedEnvelope,
  QualificationRequest,
  UUID,
} from "@/types/api";

const BASE = "/opportunities";

export async function listOpportunities(
  tenantId: string,
  params?: OpportunityListParams,
  signal?: AbortSignal,
): Promise<Page<Opportunity>> {
  return unwrapPage(
    await api.get<PaginatedEnvelope<Opportunity>>(BASE, {
      query: { ...params },
      tenantId,
      ...(signal ? { signal } : {}),
    }),
  );
}

export async function getOpportunity(
  tenantId: string,
  opportunityId: UUID,
): Promise<Opportunity> {
  return unwrap(
    await api.get<ApiEnvelope<Opportunity>>(`${BASE}/${opportunityId}`, { tenantId }),
  );
}

export async function createOpportunity(
  tenantId: string,
  payload: OpportunityCreate,
): Promise<Opportunity> {
  return unwrap(await api.post<ApiEnvelope<Opportunity>>(BASE, payload, { tenantId }));
}

export async function updateOpportunity(
  tenantId: string,
  opportunityId: UUID,
  payload: OpportunityUpdate,
): Promise<Opportunity> {
  return unwrap(
    await api.patch<ApiEnvelope<Opportunity>>(`${BASE}/${opportunityId}`, payload, {
      tenantId,
    }),
  );
}

export async function deleteOpportunity(
  tenantId: string,
  opportunityId: UUID,
): Promise<void> {
  unwrapAck(await api.del<ApiEnvelope<unknown>>(`${BASE}/${opportunityId}`, { tenantId }));
}

/** Re-score the opportunity. The backend owns the scoring rules. */
export async function qualifyOpportunity(
  tenantId: string,
  opportunityId: UUID,
  payload: QualificationRequest = {},
): Promise<Opportunity> {
  return unwrap(
    await api.post<ApiEnvelope<Opportunity>>(`${BASE}/${opportunityId}/qualify`, payload, {
      tenantId,
    }),
  );
}

/** Approve: select this opportunity for submission. */
export async function selectOpportunity(
  tenantId: string,
  opportunityId: UUID,
): Promise<Opportunity> {
  return unwrap(
    await api.post<ApiEnvelope<Opportunity>>(`${BASE}/${opportunityId}/select`, undefined, {
      tenantId,
    }),
  );
}

export async function rejectOpportunity(
  tenantId: string,
  opportunityId: UUID,
  payload: OpportunityRejectRequest,
): Promise<Opportunity> {
  return unwrap(
    await api.post<ApiEnvelope<Opportunity>>(`${BASE}/${opportunityId}/reject`, payload, {
      tenantId,
    }),
  );
}

/** Explicit state change, validated against the backend's state machine. */
export async function transitionOpportunity(
  tenantId: string,
  opportunityId: UUID,
  payload: OpportunityTransitionRequest,
): Promise<Opportunity> {
  return unwrap(
    await api.post<ApiEnvelope<Opportunity>>(
      `${BASE}/${opportunityId}/transition`,
      payload,
      { tenantId },
    ),
  );
}

/** The permitted transitions, so the UI offers only actions that can succeed. */
export async function getOpportunityStateMachine(
  tenantId: string,
): Promise<Record<string, unknown>> {
  return unwrap(
    await api.get<ApiEnvelope<Record<string, unknown>>>(`${BASE}/state-machine`, {
      tenantId,
    }),
  );
}

/* -------------------------------------------------------------------------- */
/* AI-generated listing content                                               */
/* -------------------------------------------------------------------------- */

export async function generateContent(
  tenantId: string,
  opportunityId: UUID,
  payload: ContentGenerationRequest = {},
): Promise<GeneratedContent> {
  return unwrap(
    await api.post<ApiEnvelope<GeneratedContent>>(
      `${BASE}/${opportunityId}/generate-content`,
      payload,
      // Generation calls an upstream provider, so allow more time than a
      // regular request before giving up.
      { tenantId, timeoutMs: 90_000 },
    ),
  );
}

export async function listGeneratedContent(
  tenantId: string,
  opportunityId: UUID,
): Promise<GeneratedContent[]> {
  return unwrap(
    await api.get<ApiEnvelope<GeneratedContent[]>>(`${BASE}/${opportunityId}/content`, {
      tenantId,
    }),
  );
}

/**
 * Accept, reject or edit a generated draft.
 *
 * `edited_content` carries the reviewer's changes, so the copy the user
 * actually approved is what gets stored.
 */
export async function reviewContent(
  tenantId: string,
  opportunityId: UUID,
  contentId: UUID,
  payload: ContentReviewRequest,
): Promise<GeneratedContent> {
  return unwrap(
    await api.post<ApiEnvelope<GeneratedContent>>(
      `${BASE}/${opportunityId}/content/${contentId}/review`,
      payload,
      { tenantId },
    ),
  );
}
