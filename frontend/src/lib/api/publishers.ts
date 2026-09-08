/**
 * Publishers — candidate free listing/directory sites — plus discovery.
 *
 * Discovery is deliberately asynchronous: `discover` with `run_async` enqueues
 * a background job and returns immediately, and the UI polls the run instead of
 * holding a request open (spec §24).
 */

import { MVP_PRICING_TYPE } from "@/config/enums";
import { api } from "@/lib/api/http";
import { unwrap, unwrapAck, unwrapPage, type Page } from "@/lib/api/envelope";
import type {
  ApiEnvelope,
  DiscoveryProvider,
  DiscoveryRequest,
  DiscoveryRun,
  DiscoveryRunListParams,
  JobAccepted,
  PaginatedEnvelope,
  Publisher,
  PublisherCreate,
  PublisherListParams,
  PublisherUpdate,
  QualificationRequest,
  QualificationResult,
  UUID,
} from "@/types/api";

const BASE = "/publishers";

/**
 * List publishers.
 *
 * `free_only` defaults to true and `pricing_type` is pinned to FREE: the MVP
 * only works with free listings, so paid inventory is never shown (spec §73).
 * A caller can still pass `free_only: false` — used by nothing in the UI today.
 */
export async function listPublishers(
  tenantId: string,
  params?: PublisherListParams,
  signal?: AbortSignal,
): Promise<Page<Publisher>> {
  return unwrapPage(
    await api.get<PaginatedEnvelope<Publisher>>(BASE, {
      query: {
        pricing_type: MVP_PRICING_TYPE,
        free_only: true,
        ...params,
      },
      tenantId,
      ...(signal ? { signal } : {}),
    }),
  );
}

export async function getPublisher(tenantId: string, publisherId: UUID): Promise<Publisher> {
  return unwrap(
    await api.get<ApiEnvelope<Publisher>>(`${BASE}/${publisherId}`, { tenantId }),
  );
}

export async function createPublisher(
  tenantId: string,
  payload: PublisherCreate,
): Promise<Publisher> {
  return unwrap(await api.post<ApiEnvelope<Publisher>>(BASE, payload, { tenantId }));
}

export async function updatePublisher(
  tenantId: string,
  publisherId: UUID,
  payload: PublisherUpdate,
): Promise<Publisher> {
  return unwrap(
    await api.patch<ApiEnvelope<Publisher>>(`${BASE}/${publisherId}`, payload, { tenantId }),
  );
}

export async function deletePublisher(tenantId: string, publisherId: UUID): Promise<void> {
  unwrapAck(await api.del<ApiEnvelope<unknown>>(`${BASE}/${publisherId}`, { tenantId }));
}

/**
 * Score a publisher and let the backend decide whether it qualifies.
 *
 * The decision and the scoring weights live in the backend; the UI only
 * displays the returned `ScoreBreakdown` (spec §2).
 */
export async function qualifyPublisher(
  tenantId: string,
  publisherId: UUID,
  payload: QualificationRequest = {},
): Promise<QualificationResult> {
  return unwrap(
    await api.post<ApiEnvelope<QualificationResult>>(
      `${BASE}/${publisherId}/qualify`,
      payload,
      { tenantId },
    ),
  );
}

/** Queue qualification as a background job, for a live re-crawl. */
export async function qualifyPublisherAsync(
  tenantId: string,
  publisherId: UUID,
  payload: QualificationRequest = {},
): Promise<JobAccepted> {
  return unwrap(
    await api.post<ApiEnvelope<JobAccepted>>(
      `${BASE}/${publisherId}/qualify-async`,
      payload,
      { tenantId },
    ),
  );
}

/* -------------------------------------------------------------------------- */
/* Discovery                                                                  */
/* -------------------------------------------------------------------------- */

/** Which discovery providers this workspace can actually use right now. */
export async function listDiscoveryProviders(
  tenantId: string,
): Promise<DiscoveryProvider[]> {
  return unwrap(
    await api.get<ApiEnvelope<DiscoveryProvider[]>>(`${BASE}/discovery-providers`, {
      tenantId,
    }),
  );
}

export async function listDiscoveryRuns(
  tenantId: string,
  params?: DiscoveryRunListParams,
): Promise<Page<DiscoveryRun>> {
  return unwrapPage(
    await api.get<PaginatedEnvelope<DiscoveryRun>>(`${BASE}/discovery-runs`, {
      query: { ...params },
      tenantId,
    }),
  );
}

/**
 * Start discovery.
 *
 * The response is either a completed run (synchronous) or a job acceptance
 * (asynchronous), so the caller must handle both. `free_only` is forced on.
 */
export type DiscoveryResponse =
  | { kind: "run"; run: DiscoveryRun }
  | { kind: "job"; job: JobAccepted };

function isJobAccepted(value: DiscoveryRun | JobAccepted): value is JobAccepted {
  return "job_id" in value && "poll_url" in value;
}

export async function startDiscovery(
  tenantId: string,
  payload: DiscoveryRequest,
): Promise<DiscoveryResponse> {
  const result = unwrap(
    await api.post<ApiEnvelope<DiscoveryRun | JobAccepted>>(
      `${BASE}/discover`,
      { ...payload, free_only: true },
      { tenantId },
    ),
  );

  return isJobAccepted(result) ? { kind: "job", job: result } : { kind: "run", run: result };
}
