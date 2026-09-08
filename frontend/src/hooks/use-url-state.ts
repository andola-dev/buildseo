"use client";

/**
 * Filters, search and pagination in the URL (spec §42).
 *
 * Table state lives in the query string rather than in React state, which makes
 * every view bookmarkable and shareable, and makes browser back/forward work
 * the way users expect. It also means the sidebar's filtered entries
 * (`/publishers?status=QUALIFIED`) need no separate page.
 */

import { useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

export type UrlStateValue = string | number | boolean | null | undefined;

export interface UseUrlStateOptions {
  /**
   * Replace the history entry instead of pushing one. Used for keystroke-level
   * changes (search, page size) so back doesn't have to unwind every character.
   */
  replace?: boolean;
  /** Params reset to page 1 when they change. Defaults to everything but `page`. */
  resetPageOnChange?: boolean;
}

export function useUrlState() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const get = useCallback(
    (key: string): string | null => searchParams.get(key),
    [searchParams],
  );

  const getNumber = useCallback(
    (key: string, fallback: number): number => {
      const raw = searchParams.get(key);
      if (raw === null) return fallback;
      const parsed = Number.parseInt(raw, 10);
      return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
    },
    [searchParams],
  );

  const getBoolean = useCallback(
    (key: string): boolean => searchParams.get(key) === "true",
    [searchParams],
  );

  /**
   * Apply a patch of params.
   *
   * `null`/`undefined`/`""` removes a key rather than writing an empty value,
   * so a cleared filter disappears from the URL instead of leaving `?status=`.
   */
  const setParams = useCallback(
    (patch: Record<string, UrlStateValue>, options: UseUrlStateOptions = {}) => {
      const { replace = false, resetPageOnChange = true } = options;
      const next = new URLSearchParams(searchParams.toString());

      for (const [key, value] of Object.entries(patch)) {
        if (value === null || value === undefined || value === "") {
          next.delete(key);
        } else {
          next.set(key, String(value));
        }
      }

      // Changing a filter while on page 5 would otherwise show an empty table.
      const touchedNonPage = Object.keys(patch).some((key) => key !== "page");
      if (resetPageOnChange && touchedNonPage && !("page" in patch)) {
        next.delete("page");
      }

      const query = next.toString();
      const url = query ? `${pathname}?${query}` : pathname;

      if (replace) router.replace(url, { scroll: false });
      else router.push(url, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  const clearParams = useCallback(
    (keys: readonly string[]) => {
      const patch: Record<string, null> = {};
      for (const key of keys) patch[key] = null;
      setParams(patch, { replace: true });
    },
    [setParams],
  );

  /** How many params are currently set, for a "Clear filters (3)" affordance. */
  const activeCount = useCallback(
    (keys: readonly string[]): number =>
      keys.filter((key) => {
        const value = searchParams.get(key);
        return value !== null && value !== "";
      }).length,
    [searchParams],
  );

  return useMemo(
    () => ({ get, getNumber, getBoolean, setParams, clearParams, activeCount, searchParams }),
    [get, getNumber, getBoolean, setParams, clearParams, activeCount, searchParams],
  );
}
