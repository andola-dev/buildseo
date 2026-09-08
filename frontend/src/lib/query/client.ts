import { QueryClient } from "@tanstack/react-query";

import { isApiError } from "@/lib/api/errors";

/**
 * Query defaults tuned for a dense B2B data application.
 *
 * - `retry` never repeats a 4xx: a 403 or 422 will not become a 200, and
 *   retrying it just delays the error state the user needs to see.
 * - `refetchOnWindowFocus` is off. Tables here carry selections and inline
 *   review state, and refetching under the user's cursor on tab focus loses it.
 * - `throwOnError` is off so each screen renders its own `ErrorState` with a
 *   retry action rather than escalating to an error boundary (spec §39).
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: false,
        refetchOnReconnect: true,
        throwOnError: false,
        retry: (failureCount, error) => {
          if (isApiError(error) && !error.isRetryable) return false;
          return failureCount < 2;
        },
        retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
      },
      mutations: {
        // A mutation is a user-initiated write; silently repeating it could
        // duplicate a submission. Retries are opt-in per mutation.
        retry: false,
        throwOnError: false,
      },
    },
  });
}
