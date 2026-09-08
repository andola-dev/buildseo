"use client";

import { useEffect, useState } from "react";

/**
 * Subscribe to a media query.
 *
 * Starts `false` on the server and during the first client render so markup
 * matches and hydration doesn't warn; the real value lands in the effect.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    const list = window.matchMedia(query);
    setMatches(list.matches);

    const onChange = (event: MediaQueryListEvent) => setMatches(event.matches);
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

/** Below the `md` breakpoint the sidebar becomes a drawer (spec §43). */
export function useIsMobile(): boolean {
  return useMediaQuery("(max-width: 767px)");
}

/** Between `md` and `xl` the sidebar defaults to the icon rail. */
export function useIsTablet(): boolean {
  return useMediaQuery("(min-width: 768px) and (max-width: 1279px)");
}
