/**
 * Display formatters.
 *
 * Centralised so a date or a metric reads the same on every screen. All of
 * these tolerate `null`/`undefined` and render an em dash, because most metric
 * fields on the API are nullable until the backend has actually measured them.
 */

const EM_DASH = "—";

function parseDate(value: string | number | Date | null | undefined): Date | null {
  if (value === null || value === undefined) return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** e.g. "12 Mar 2026" */
export function formatDate(value: string | Date | null | undefined): string {
  const date = parseDate(value);
  if (!date) return EM_DASH;
  return new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(date);
}

/** e.g. "12 Mar 2026, 14:05" */
export function formatDateTime(value: string | Date | null | undefined): string {
  const date = parseDate(value);
  if (!date) return EM_DASH;
  return new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

/** e.g. "3 days ago", "in 2 hours" */
export function formatRelative(value: string | Date | null | undefined): string {
  const date = parseDate(value);
  if (!date) return EM_DASH;

  const deltaSeconds = (date.getTime() - Date.now()) / 1000;
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

  const thresholds: [Intl.RelativeTimeFormatUnit, number][] = [
    ["year", 60 * 60 * 24 * 365],
    ["month", 60 * 60 * 24 * 30],
    ["week", 60 * 60 * 24 * 7],
    ["day", 60 * 60 * 24],
    ["hour", 60 * 60],
    ["minute", 60],
  ];

  for (const [unit, seconds] of thresholds) {
    if (Math.abs(deltaSeconds) >= seconds) {
      return formatter.format(Math.round(deltaSeconds / seconds), unit);
    }
  }

  return formatter.format(Math.round(deltaSeconds), "second");
}

/** e.g. 1284 → "1,284" */
export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return EM_DASH;
  return new Intl.NumberFormat().format(value);
}

/** Compact form for dense metric cells: 12500 → "12.5K" */
export function formatCompactNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return EM_DASH;
  return new Intl.NumberFormat(undefined, {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

/** Scores are 0–100 and shown without decimals. */
export function formatScore(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return EM_DASH;
  return String(Math.round(value));
}

export function formatPercent(value: number | null | undefined, fractionDigits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return EM_DASH;
  return `${value.toFixed(fractionDigits)}%`;
}

/**
 * Monetary amounts arrive as decimal strings so precision is not lost in JSON.
 */
export function formatCurrency(
  value: string | number | null | undefined,
  currency = "USD",
): string {
  if (value === null || value === undefined || value === "") return EM_DASH;
  const amount = typeof value === "string" ? Number.parseFloat(value) : value;
  if (Number.isNaN(amount)) return EM_DASH;
  return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(amount);
}

/** Strip the scheme and any trailing slash for display: "https://a.com/" → "a.com" */
export function displayDomain(value: string | null | undefined): string {
  if (!value) return EM_DASH;
  return value.replace(/^https?:\/\//i, "").replace(/\/+$/, "");
}

/**
 * Initials for an avatar fallback.
 *
 * When falling back to an email address only the local part is used: the domain
 * would otherwise supply the second initial, turning
 * `priya.sharma@example.com` into "PC" instead of "PS".
 */
export function initials(name: string | null | undefined, email?: string | null): string {
  const trimmedName = name?.trim();
  const localPart = email?.trim().split("@")[0];
  const source = trimmedName || localPart || "";
  if (!source) return "?";

  const parts = source.split(/[\s._-]+/).filter(Boolean);
  const first = parts[0]?.charAt(0) ?? "";
  const second = parts.length > 1 ? (parts[parts.length - 1]?.charAt(0) ?? "") : "";
  return (first + second).toUpperCase() || "?";
}

/** Best available display name for a user record. */
export function userDisplayName(user: {
  full_name?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  email?: string;
} | null | undefined): string {
  if (!user) return EM_DASH;
  if (user.full_name) return user.full_name;
  const joined = [user.first_name, user.last_name].filter(Boolean).join(" ").trim();
  if (joined) return joined;
  return user.email ?? EM_DASH;
}

export function truncate(value: string | null | undefined, max = 80): string {
  if (!value) return EM_DASH;
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

export { EM_DASH };
