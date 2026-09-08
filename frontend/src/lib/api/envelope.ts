import { ApiError } from "@/lib/api/errors";
import type { ApiEnvelope, PaginatedEnvelope, PaginationMeta } from "@/types/api";

/**
 * A collection response, flattened for the UI.
 *
 * `items` and `meta` are kept separate because TanStack Table needs the rows
 * while the pagination footer needs the counters.
 */
export interface Page<T> {
  items: T[];
  meta: PaginationMeta;
}

function malformed(): ApiError {
  return new ApiError({
    status: 0,
    code: "MALFORMED_RESPONSE",
    message: "We received an unexpected response from the server.",
  });
}

/** Unwrap `{ data }` from a single-resource response. */
export function unwrap<T>(envelope: ApiEnvelope<T> | undefined): T {
  if (!envelope || !("data" in envelope)) throw malformed();
  return envelope.data;
}

/** Unwrap `{ data, meta }` from a collection response. */
export function unwrapPage<T>(envelope: PaginatedEnvelope<T> | undefined): Page<T> {
  if (!envelope || !Array.isArray(envelope.data) || !envelope.meta) throw malformed();
  return { items: envelope.data, meta: envelope.meta };
}

/**
 * Some endpoints return `ApiResponse[dict]` for an action with no resource
 * (logout, revoke). Callers only need to know it succeeded.
 */
export function unwrapAck(envelope: ApiEnvelope<unknown> | undefined): void {
  if (!envelope) throw malformed();
}
