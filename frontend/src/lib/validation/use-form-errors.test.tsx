import { describe, expect, it } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { z } from "zod";

import { apiErrorFromBody } from "@/lib/api/errors";
import { useFormErrors } from "@/lib/validation/use-form-errors";

const schema = z.object({
  name: z.string().min(2, "Too short."),
  nested: z.object({ count: z.number() }),
});

describe("useFormErrors", () => {
  it("stores Zod issues under dotted field paths so they match the backend's naming", () => {
    const { result } = renderHook(() => useFormErrors());

    act(() => {
      result.current.validate(schema, { name: "a", nested: { count: "x" } });
    });

    expect(result.current.errors.name).toBe("Too short.");
    expect(result.current.errors["nested.count"]).toBeDefined();
  });

  it("returns the parsed value and clears errors on success", () => {
    const { result } = renderHook(() => useFormErrors());

    let parsed: unknown;
    act(() => {
      parsed = result.current.validate(schema, { name: "Acme", nested: { count: 1 } });
    });

    expect(parsed).toEqual({ name: "Acme", nested: { count: 1 } });
    expect(result.current.errors).toEqual({});
  });

  it("maps a backend 422 onto the same fields and suppresses the banner", () => {
    const { result } = renderHook(() => useFormErrors());

    const error = apiErrorFromBody(422, {
      detail: [{ loc: ["body", "name"], msg: "Already taken", type: "value_error" }],
    });

    let matched = false;
    act(() => {
      matched = result.current.applyServerError(error);
    });

    expect(matched).toBe(true);
    expect(result.current.fieldError("name")).toBe("Already taken");
    // No duplicate banner when the message already sits on a field.
    expect(result.current.formError).toBeNull();
  });

  it("shows a banner when the failure belongs to no field", () => {
    const { result } = renderHook(() => useFormErrors());

    const error = apiErrorFromBody(409, {
      error: { code: "DUPLICATE_RESOURCE", message: "Already exists" },
    });

    let matched = true;
    act(() => {
      matched = result.current.applyServerError(error);
    });

    expect(matched).toBe(false);
    expect(result.current.formError).toBe("That already exists.");
  });

  it("does not leak a non-ApiError value into the message", () => {
    const { result } = renderHook(() => useFormErrors());

    act(() => {
      result.current.applyServerError({ token: "secret" });
    });

    expect(result.current.formError).toBe("Something went wrong. Please try again.");
  });

  it("clears both field and form errors", () => {
    const { result } = renderHook(() => useFormErrors());

    act(() => {
      result.current.validate(schema, { name: "a", nested: { count: 1 } });
      result.current.setFormError("boom");
    });
    act(() => {
      result.current.clear();
    });

    expect(result.current.errors).toEqual({});
    expect(result.current.formError).toBeNull();
  });
});
