"use client";

import { useEffect, useState } from "react";

/**
 * Debounce a rapidly-changing value (spec §53).
 *
 * Used by search inputs so typing produces one request rather than one per
 * keystroke. 300ms is the default: long enough to coalesce a burst of typing,
 * short enough that the table doesn't feel stalled.
 */
export function useDebouncedValue<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
