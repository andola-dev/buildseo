import type { FieldIssue } from "@/types/api";

/**
 * The one error type the application handles (spec §56).
 *
 * Every failure — HTTP error, network failure, timeout, unparseable body —
 * arrives at the UI as an `ApiError` with a user-safe `message`. Backend
 * internals never reach the screen: the transport substitutes copy from
 * `ERROR_MESSAGES` for anything that isn't already caller-safe.
 */
export class ApiError extends Error {
  /** HTTP status, or 0 for a network/transport failure. */
  readonly status: number;
  /** Stable machine code from the backend's error envelope. */
  readonly code: string;
  /** Field-level issues, flattened from a 422 response. */
  readonly details: FieldIssue[];
  /** Structured context the backend attached, for debugging only. */
  readonly context?: Record<string, unknown>;

  constructor(options: {
    status: number;
    code: string;
    message: string;
    details?: FieldIssue[];
    context?: Record<string, unknown>;
  }) {
    super(options.message);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code;
    this.details = options.details ?? [];
    if (options.context) this.context = options.context;
  }

  /** A transport failure raised by the client itself (status 0). */
  get isNetworkError(): boolean {
    return this.status === 0;
  }

  /**
   * The service could not be reached, however that was reported.
   *
   * A connectivity failure does not always arrive as status 0: the session
   * route handlers proxy to FastAPI and report an unreachable backend as a 503
   * carrying `NETWORK_ERROR`. Both are the same thing to the user, and the UI
   * must not title one of them "Sign-in failed" while its body says the server
   * is unreachable.
   */
  get isConnectivityError(): boolean {
    return (
      this.status === 0 ||
      this.status === 503 ||
      this.status === 504 ||
      this.code === "NETWORK_ERROR" ||
      this.code === "TIMEOUT"
    );
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  get isValidationError(): boolean {
    return this.status === 422 || this.status === 400;
  }

  /** 5xx and network failures are worth retrying; 4xx are not. */
  get isRetryable(): boolean {
    return this.status === 0 || this.status >= 500 || this.status === 429;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

/* -------------------------------------------------------------------------- */
/* Copy                                                                       */
/* -------------------------------------------------------------------------- */

/**
 * User-facing copy for the backend's error codes (app/core/exceptions.py).
 *
 * A code that is missing here falls back to the backend's own `message`, which
 * the API contract guarantees is caller-safe, and then to a generic line.
 */
export const ERROR_MESSAGES: Record<string, string> = {
  // Authentication
  AUTHENTICATION_FAILED: "Unable to sign in. Please check your email and password.",
  INVALID_CREDENTIALS: "Unable to sign in. Please check your email and password.",
  TOKEN_EXPIRED: "Your session has expired. Please sign in again.",
  TOKEN_REVOKED: "Your session is no longer valid. Please sign in again.",
  INVALID_TOKEN: "Your session is no longer valid. Please sign in again.",
  USER_INACTIVE: "This account has been deactivated. Contact your workspace owner.",

  // Authorization and tenancy
  PERMISSION_DENIED: "You do not have permission to do that.",
  TENANT_ACCESS_DENIED: "You do not have access to this workspace.",
  TENANT_CONTEXT_REQUIRED: "Select a workspace to continue.",
  TENANT_INACTIVE: "This workspace is not active.",

  // Resources
  RESOURCE_NOT_FOUND: "We couldn't find what you were looking for.",
  CONFLICT: "That change conflicts with the current state. Refresh and try again.",
  DUPLICATE_RESOURCE: "That already exists.",
  IDEMPOTENCY_KEY_REUSED: "This request was already submitted.",

  // Validation and business rules
  VALIDATION_ERROR: "Please correct the highlighted fields.",
  BUSINESS_RULE_VIOLATION: "That action isn't allowed right now.",
  PAID_PLACEMENT_NOT_ALLOWED:
    "This workspace supports free listings only. Paid placements are not available.",
  INVALID_STATE_TRANSITION: "That status change isn't allowed from the current state.",
  SUBMISSION_ERROR: "This submission can't be advanced right now.",

  // Credentials (BYOK)
  CREDENTIAL_ERROR: "We couldn't use that credential.",
  CREDENTIAL_NOT_CONFIGURED:
    "No provider credential is configured. Add one in Settings → AI Providers.",
  CREDENTIAL_DECRYPTION_FAILED:
    "This credential could not be read. Replace it in Settings → AI Providers.",

  // Upstream providers
  PROVIDER_ERROR: "The provider returned an error. Try again shortly.",
  PROVIDER_UNAVAILABLE: "The provider is unavailable. Try again shortly.",
  PROVIDER_NOT_SUPPORTED: "That provider isn't supported.",
  PROVIDER_TIMEOUT: "The provider took too long to respond. Try again.",
  RESPONSE_TOO_LARGE: "The provider returned too much data to process.",

  // Infrastructure
  RATE_LIMIT_EXCEEDED: "Too many requests. Please wait a moment and try again.",
  INTERNAL_ERROR: "Something went wrong on our end. Please try again.",

  // Transport-level codes raised by the client itself
  NETWORK_ERROR: "We couldn't reach the server. Check your connection and try again.",
  TIMEOUT: "The request took too long. Please try again.",
  MALFORMED_RESPONSE: "We received an unexpected response from the server.",
};

/** Last-resort copy per HTTP status class. */
const STATUS_MESSAGES: Record<number, string> = {
  400: "That request wasn't valid.",
  401: "Your session has expired. Please sign in again.",
  403: "You do not have permission to do that.",
  404: "We couldn't find what you were looking for.",
  409: "That change conflicts with the current state. Refresh and try again.",
  422: "Please correct the highlighted fields.",
  429: "Too many requests. Please wait a moment and try again.",
  500: "Something went wrong on our end. Please try again.",
  502: "The service is temporarily unavailable. Please try again.",
  503: "The service is temporarily unavailable. Please try again.",
  504: "The request took too long. Please try again.",
};

export function messageForStatus(status: number): string {
  return (
    STATUS_MESSAGES[status] ??
    (status >= 500
      ? "Something went wrong on our end. Please try again."
      : "That request could not be completed.")
  );
}

/**
 * Resolve the copy shown to the user, preferring our own wording for known
 * codes over the backend's, then the backend's caller-safe message, then a
 * status-based fallback.
 */
export function resolveMessage(
  code: string | undefined,
  backendMessage: string | undefined,
  status: number,
): string {
  if (code && ERROR_MESSAGES[code]) return ERROR_MESSAGES[code];
  if (backendMessage && backendMessage.trim().length > 0) return backendMessage;
  return messageForStatus(status);
}

/* -------------------------------------------------------------------------- */
/* Parsing                                                                    */
/* -------------------------------------------------------------------------- */

interface BackendErrorEnvelope {
  error?: { code?: string; message?: string; details?: Record<string, unknown> };
  detail?: unknown;
}

interface PydanticIssue {
  loc?: (string | number)[];
  msg?: string;
  type?: string;
}

/**
 * Flatten FastAPI's 422 body into field issues.
 *
 * `loc` is a path such as `["body", "target_link_count"]`; the leading
 * `body`/`query`/`path` segment is dropped so the remainder matches the form
 * field name. Nested paths become dotted (`["body","a","b"]` → `a.b`).
 */
function parsePydanticDetail(detail: unknown): FieldIssue[] {
  if (!Array.isArray(detail)) return [];

  return detail.flatMap((raw): FieldIssue[] => {
    if (typeof raw !== "object" || raw === null) return [];
    const issue = raw as PydanticIssue;
    const loc = Array.isArray(issue.loc) ? issue.loc : [];
    const path = loc
      .filter((part) => part !== "body" && part !== "query" && part !== "path")
      .map(String);

    const field = path.length > 0 ? path.join(".") : "_root";
    const message = issue.msg ?? "This value isn't valid.";
    return [issue.type ? { field, message, code: issue.type } : { field, message }];
  });
}

/**
 * Read field issues out of the backend's own error envelope.
 *
 * `ErrorDetail.details` is an open object; a `fields` map (`{ field: message }`)
 * or a `fields` array is understood, anything else is kept as context only.
 */
function parseEnvelopeDetails(details: Record<string, unknown> | undefined): FieldIssue[] {
  if (!details) return [];

  const fields = details.fields;

  if (Array.isArray(fields)) {
    return fields.flatMap((entry): FieldIssue[] => {
      if (typeof entry !== "object" || entry === null) return [];
      const record = entry as Record<string, unknown>;
      const field = typeof record.field === "string" ? record.field : null;
      const message = typeof record.message === "string" ? record.message : null;
      return field && message ? [{ field, message }] : [];
    });
  }

  if (typeof fields === "object" && fields !== null) {
    return Object.entries(fields).flatMap(([field, message]) =>
      typeof message === "string" ? [{ field, message }] : [],
    );
  }

  return [];
}

/**
 * Build an `ApiError` from a non-2xx response body.
 *
 * Handles both shapes the backend can produce: its own
 * `{ error: { code, message, details } }` envelope, and FastAPI's default
 * `{ detail: [...] }` for request-validation failures.
 */
export function apiErrorFromBody(status: number, body: unknown): ApiError {
  if (typeof body !== "object" || body === null) {
    return new ApiError({
      status,
      code: status === 0 ? "NETWORK_ERROR" : "HTTP_ERROR",
      message: messageForStatus(status),
    });
  }

  const envelope = body as BackendErrorEnvelope;

  if (envelope.error && typeof envelope.error === "object") {
    const { code, message, details } = envelope.error;
    const resolvedCode = code ?? "HTTP_ERROR";
    const error = new ApiError({
      status,
      code: resolvedCode,
      message: resolveMessage(code, message, status),
      details: parseEnvelopeDetails(details),
      ...(details ? { context: details } : {}),
    });
    return error;
  }

  if (envelope.detail !== undefined) {
    const issues = parsePydanticDetail(envelope.detail);
    if (issues.length > 0) {
      return new ApiError({
        status,
        code: "VALIDATION_ERROR",
        message: ERROR_MESSAGES.VALIDATION_ERROR ?? messageForStatus(status),
        details: issues,
      });
    }
    // A plain-string `detail` is FastAPI's own copy (e.g. "Not Found"). It is
    // safe but unhelpful, so prefer our status copy.
    return new ApiError({
      status,
      code: "HTTP_ERROR",
      message: messageForStatus(status),
    });
  }

  return new ApiError({
    status,
    code: "HTTP_ERROR",
    message: messageForStatus(status),
  });
}

/** Map field issues onto form state: `{ fieldName: message }`. */
export function fieldErrorMap(error: unknown): Record<string, string> {
  if (!isApiError(error)) return {};
  const map: Record<string, string> = {};
  for (const issue of error.details) {
    if (!(issue.field in map)) map[issue.field] = issue.message;
  }
  return map;
}

/** The message to show in a toast or error panel for any thrown value. */
export function errorMessage(error: unknown): string {
  if (isApiError(error)) return error.message;
  if (error instanceof Error && error.message) return error.message;
  return "Something went wrong. Please try again.";
}
