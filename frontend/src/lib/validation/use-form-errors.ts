"use client";

/**
 * Field-error state for a form (spec §41).
 *
 * Holds two sources in one place: issues found by Zod before submitting, and
 * field errors mapped out of a backend 422. Because both land in the same map,
 * a field renders its error identically whichever produced it.
 */

import { useCallback, useState } from "react";
import type { ZodType } from "zod";

import { fieldErrorMap, isApiError } from "@/lib/api/errors";

export interface FormErrors {
  errors: Record<string, string>;
  /** Error not tied to a field, e.g. a business-rule violation. */
  formError: string | null;
  setFormError: (message: string | null) => void;
  clear: () => void;
  /** Validate with Zod, storing issues and returning the parsed value. */
  validate: <T>(schema: ZodType<T>, value: unknown) => T | null;
  /** Map a thrown `ApiError` onto fields; returns true if any field matched. */
  applyServerError: (error: unknown) => boolean;
  fieldError: (name: string) => string | undefined;
}

export function useFormErrors(): FormErrors {
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  const clear = useCallback(() => {
    setErrors({});
    setFormError(null);
  }, []);

  const validate = useCallback(<T,>(schema: ZodType<T>, value: unknown): T | null => {
    const result = schema.safeParse(value);

    if (result.success) {
      setErrors({});
      return result.data;
    }

    const mapped: Record<string, string> = {};
    for (const issue of result.error.issues) {
      // Nested paths are dotted so they match the backend's field naming.
      const path = issue.path.filter((part) => typeof part !== "symbol").join(".");
      const key = path || "_root";
      if (!(key in mapped)) mapped[key] = issue.message;
    }

    setErrors(mapped);
    return null;
  }, []);

  const applyServerError = useCallback((error: unknown): boolean => {
    if (!isApiError(error)) {
      setFormError("Something went wrong. Please try again.");
      return false;
    }

    const mapped = fieldErrorMap(error);
    const fieldKeys = Object.keys(mapped).filter((key) => key !== "_root");

    setErrors(mapped);
    // Show the banner only when nothing landed on a field, so the user isn't
    // told twice about the same problem.
    setFormError(fieldKeys.length > 0 ? null : error.message);

    return fieldKeys.length > 0;
  }, []);

  const fieldError = useCallback(
    (name: string): string | undefined => errors[name],
    [errors],
  );

  return {
    errors,
    formError,
    setFormError,
    clear,
    validate,
    applyServerError,
    fieldError,
  };
}
