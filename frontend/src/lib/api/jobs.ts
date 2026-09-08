/**
 * Background jobs.
 *
 * Long-running work (discovery, qualification, verification) is enqueued by the
 * resource endpoints and observed here, which is what lets the UI stay
 * responsive instead of blocking on a slow crawl (spec §24).
 */

import { api } from "@/lib/api/http";
import { unwrap, unwrapPage, type Page } from "@/lib/api/envelope";
import type { ApiEnvelope, Job, JobListParams, PaginatedEnvelope, UUID } from "@/types/api";

export async function listJobs(
  tenantId: string,
  params?: JobListParams,
): Promise<Page<Job>> {
  return unwrapPage(
    await api.get<PaginatedEnvelope<Job>>("/jobs", { query: { ...params }, tenantId }),
  );
}

export async function getJob(tenantId: string, jobId: UUID): Promise<Job> {
  return unwrap(await api.get<ApiEnvelope<Job>>(`/jobs/${jobId}`, { tenantId }));
}

export async function listTaskTypes(tenantId: string): Promise<string[]> {
  return unwrap(await api.get<ApiEnvelope<string[]>>("/jobs/task-types", { tenantId }));
}
