"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { STORAGE_KEYS } from "@/config/app";
import { useIsMobile, useIsTablet } from "@/hooks/use-media-query";
import { readLocal, writeLocal } from "@/lib/utils/storage";

interface SidebarContextValue {
  /** Icon-rail mode on desktop. */
  collapsed: boolean;
  toggleCollapsed: () => void;
  setCollapsed: (collapsed: boolean) => void;

  /** Drawer state below `md`, where the sidebar is a Sheet (spec §43). */
  mobileOpen: boolean;
  setMobileOpen: (open: boolean) => void;

  isMobile: boolean;
}

const SidebarContext = createContext<SidebarContextValue | null>(null);

/**
 * Sidebar layout state.
 *
 * Collapsing is a CSS-variable and attribute change, never a navigation, so
 * expanding or collapsing does not remount the page or refetch anything
 * (spec §6). The preference is persisted locally.
 */
export function SidebarProvider({ children }: { children: React.ReactNode }) {
  const isMobile = useIsMobile();
  const isTablet = useIsTablet();

  const [collapsed, setCollapsedState] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  /**
   * Read the stored preference after mount.
   *
   * Server and first client render both use `collapsed: false` so the markup
   * matches; the stored value is applied immediately afterwards. On a tablet
   * the rail is the default when nothing was stored (spec §43).
   */
  useEffect(() => {
    const stored = readLocal(STORAGE_KEYS.sidebarCollapsed);
    if (stored !== null) setCollapsedState(stored === "true");
    else if (isTablet) setCollapsedState(true);
    setHydrated(true);
    // Runs once: later breakpoint changes must not override an explicit choice.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setCollapsed = useCallback((next: boolean) => {
    setCollapsedState(next);
    writeLocal(STORAGE_KEYS.sidebarCollapsed, String(next));
  }, []);

  const toggleCollapsed = useCallback(() => {
    setCollapsedState((current) => {
      const next = !current;
      writeLocal(STORAGE_KEYS.sidebarCollapsed, String(next));
      return next;
    });
  }, []);

  /** Close the drawer on navigation-sized viewport changes. */
  useEffect(() => {
    if (!isMobile) setMobileOpen(false);
  }, [isMobile]);

  /** Ctrl/Cmd+B toggles the sidebar, the convention users expect. */
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key.toLowerCase() === "b" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        if (isMobile) setMobileOpen((open) => !open);
        else toggleCollapsed();
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isMobile, toggleCollapsed]);

  const value = useMemo<SidebarContextValue>(
    () => ({
      // Before hydration the expanded layout is used, matching SSR output.
      collapsed: hydrated ? collapsed : false,
      toggleCollapsed,
      setCollapsed,
      mobileOpen,
      setMobileOpen,
      isMobile,
    }),
    [hydrated, collapsed, toggleCollapsed, setCollapsed, mobileOpen, isMobile],
  );

  return <SidebarContext.Provider value={value}>{children}</SidebarContext.Provider>;
}

export function useSidebar(): SidebarContextValue {
  const context = useContext(SidebarContext);
  if (!context) throw new Error("useSidebar must be used inside <SidebarProvider>");
  return context;
}
