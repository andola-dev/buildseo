import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { PermissionGate, RequirePermission } from "@/components/shared/permission-gate";

/**
 * The gate reads from `usePermissions`, which is mocked here so the gating
 * logic can be tested in isolation from session loading. `AuthProvider`'s
 * end-to-end behaviour is covered in `lib/auth/auth-provider.test.tsx`.
 */
const granted = new Set<string>();

vi.mock("@/lib/permissions/use-permissions", () => ({
  usePermissions: () => ({
    permissions: granted,
    can: (permission?: string | null) => (permission ? granted.has(permission) : true),
    canAny: (required: readonly string[]) =>
      required.length === 0 || required.some((permission) => granted.has(permission)),
    canAll: (required: readonly string[]) =>
      required.every((permission) => granted.has(permission)),
  }),
  matchesPermission: (set: ReadonlySet<string>, code: string) => set.has(code),
}));

function withGrants(codes: string[], run: () => void) {
  granted.clear();
  for (const code of codes) granted.add(code);
  run();
}

describe("PermissionGate", () => {
  it("hides the action when the permission is absent", () => {
    withGrants([], () => {
      render(
        <PermissionGate permission="campaign.create">
          <button>New campaign</button>
        </PermissionGate>,
      );
    });

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("renders the action when the permission is granted", () => {
    withGrants(["campaign.create"], () => {
      render(
        <PermissionGate permission="campaign.create">
          <button>New campaign</button>
        </PermissionGate>,
      );
    });

    expect(screen.getByRole("button", { name: "New campaign" })).toBeInTheDocument();
  });

  it("renders a fallback instead of nothing when one is supplied", () => {
    withGrants([], () => {
      render(
        <PermissionGate permission="campaign.create" fallback={<span>Read-only</span>}>
          <button>New campaign</button>
        </PermissionGate>,
      );
    });

    expect(screen.getByText("Read-only")).toBeInTheDocument();
  });

  it("disables rather than hides in disable mode, and says why", () => {
    withGrants([], () => {
      render(
        <PermissionGate permission="campaign.create" mode="disable">
          <button>New campaign</button>
        </PermissionGate>,
      );
    });

    const wrapper = screen.getByTitle("You don't have permission to do this");
    expect(wrapper).toHaveAttribute("aria-disabled");
    expect(wrapper.className).toContain("pointer-events-none");
    // The control stays discoverable so the user knows the feature exists.
    expect(screen.getByRole("button", { name: "New campaign" })).toBeInTheDocument();
  });

  it("requires any of a set", () => {
    withGrants(["submission.read"], () => {
      render(
        <PermissionGate anyOf={["submission.approve", "submission.read"]}>
          <span>Visible</span>
        </PermissionGate>,
      );
    });
    expect(screen.getByText("Visible")).toBeInTheDocument();
  });

  it("requires all of a set", () => {
    withGrants(["submission.read"], () => {
      render(
        <PermissionGate allOf={["submission.read", "submission.approve"]}>
          <span>Hidden</span>
        </PermissionGate>,
      );
    });
    expect(screen.queryByText("Hidden")).not.toBeInTheDocument();
  });

  it("renders children when no permission is required", () => {
    withGrants([], () => {
      render(
        <PermissionGate>
          <span>Always</span>
        </PermissionGate>,
      );
    });
    expect(screen.getByText("Always")).toBeInTheDocument();
  });
});

describe("RequirePermission", () => {
  it("renders the fallback for a route the user can't access", () => {
    withGrants([], () => {
      render(
        <RequirePermission permission="audit.read" fallback={<span>No access</span>}>
          <span>Audit log</span>
        </RequirePermission>,
      );
    });

    expect(screen.getByText("No access")).toBeInTheDocument();
    expect(screen.queryByText("Audit log")).not.toBeInTheDocument();
  });

  it("renders the page when the permission is granted", () => {
    withGrants(["audit.read"], () => {
      render(
        <RequirePermission permission="audit.read" fallback={<span>No access</span>}>
          <span>Audit log</span>
        </RequirePermission>,
      );
    });

    expect(screen.getByText("Audit log")).toBeInTheDocument();
  });
});
