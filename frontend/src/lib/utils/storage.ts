/**
 * Guarded `localStorage` access.
 *
 * Storage throws in private-mode Safari and when a browser blocks site data, so
 * every access is wrapped. Nothing sensitive is ever stored here — only UI
 * preferences and the last-used workspace id (spec §48).
 */

export function readLocal(key: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeLocal(key: string, value: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // A full or blocked store is not worth surfacing: the preference simply
    // won't persist.
  }
}

export function removeLocal(key: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(key);
  } catch {
    // Ignored, as above.
  }
}

export function readLocalBoolean(key: string, fallback: boolean): boolean {
  const raw = readLocal(key);
  if (raw === null) return fallback;
  return raw === "true";
}

export function readLocalNumber(key: string, fallback: number): number {
  const raw = readLocal(key);
  if (raw === null) return fallback;
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}
