"use client";

/**
 * Shared state for a server-driven list screen.
 *
 * Search, filters, sorting and pagination all live in the URL (spec §42), so
 * every list view is bookmarkable and the sidebar's filtered entries
 * (`/publishers?status=QUALIFIED`) are the same page with different query
 * state. This hook is the one place that translates between the URL and the
 * shape the API client wants.
 */

import { useCallback, useMemo } from "react";
import type { OnChangeFn, SortingState } from "@tanstack/react-table";

import { DEFAULT_PAGE_SIZE } from "@/config/app";
import { useUrlState } from "@/hooks/use-url-state";

export interface UseListStateOptions {
  /** Filter params this screen reads, so "Clear" knows what to remove. */
  filterKeys: readonly string[];
  defaultSort?: string;
  defaultOrder?: "asc" | "desc";
}

export interface ListState {
  page: number;
  pageSize: number;
  search: string;
  sort: string | null;
  order: "asc" | "desc";

  /** TanStack Table's controlled sorting state. */
  sorting: SortingState;
  onSortingChange: OnChangeFn<SortingState>;

  setPage: (page: number) => void;
  setPageSize: (pageSize: number) => void;
  setSearch: (search: string) => void;

  /** Read one filter value from the URL. */
  filter: (key: string) => string | null;
  setFilter: (key: string, value: string | null) => void;
  setFilters: (patch: Record<string, string | null>) => void;

  activeFilterCount: number;
  resetFilters: () => void;

  /** Page/sort/search params, ready to spread into an API call. */
  pageParams: {
    page: number;
    page_size: number;
    q?: string;
    sort?: string;
    order: "asc" | "desc";
  };
}

export function useListState(options: UseListStateOptions): ListState {
  const { filterKeys, defaultSort, defaultOrder = "desc" } = options;
  const { get, getNumber, setParams, clearParams, activeCount } = useUrlState();

  const page = getNumber("page", 1);
  const pageSize = getNumber("page_size", DEFAULT_PAGE_SIZE);
  const search = get("q") ?? "";
  const sort = get("sort") ?? defaultSort ?? null;
  const rawOrder = get("order");
  const order: "asc" | "desc" = rawOrder === "asc" ? "asc" : rawOrder === "desc" ? "desc" : defaultOrder;

  const sorting = useMemo<SortingState>(
    () => (sort ? [{ id: sort, desc: order === "desc" }] : []),
    [sort, order],
  );

  const onSortingChange = useCallback<OnChangeFn<SortingState>>(
    (updater) => {
      const next = typeof updater === "function" ? updater(sorting) : updater;
      const first = next[0];

      if (!first) {
        setParams({ sort: null, order: null }, { replace: true });
        return;
      }

      setParams(
        { sort: first.id, order: first.desc ? "desc" : "asc" },
        { replace: true },
      );
    },
    [setParams, sorting],
  );

  const setPage = useCallback(
    // Page 1 is the default, so it is omitted from the URL rather than written.
    (next: number) => setParams({ page: next <= 1 ? null : next }, { replace: false }),
    [setParams],
  );

  const setPageSize = useCallback(
    (next: number) =>
      setParams(
        { page_size: next === DEFAULT_PAGE_SIZE ? null : next, page: null },
        { replace: true },
      ),
    [setParams],
  );

  const setSearch = useCallback(
    // Replace rather than push: typing should not fill the history stack.
    (next: string) => setParams({ q: next || null }, { replace: true }),
    [setParams],
  );

  const setFilter = useCallback(
    (key: string, value: string | null) => setParams({ [key]: value }),
    [setParams],
  );

  const setFilters = useCallback(
    (patch: Record<string, string | null>) => setParams(patch),
    [setParams],
  );

  const resetFilters = useCallback(
    () => clearParams([...filterKeys, "q", "page"]),
    [clearParams, filterKeys],
  );

  const pageParams = useMemo(
    () => ({
      page,
      page_size: pageSize,
      ...(search ? { q: search } : {}),
      ...(sort ? { sort } : {}),
      order,
    }),
    [page, pageSize, search, sort, order],
  );

  return {
    page,
    pageSize,
    search,
    sort,
    order,
    sorting,
    onSortingChange,
    setPage,
    setPageSize,
    setSearch,
    filter: get,
    setFilter,
    setFilters,
    activeFilterCount: activeCount([...filterKeys, "q"]),
    resetFilters,
    pageParams,
  };
}
