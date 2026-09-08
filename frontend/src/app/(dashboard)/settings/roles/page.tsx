import type { Metadata } from "next";

import { NoAccessState } from "@/components/feedback/no-access-state";
import { RequirePermission } from "@/components/shared/permission-gate";
import { PERM } from "@/config/permissions";
import { RolesView } from "@/features/roles/components/roles-view";

export const metadata: Metadata = { title: "Roles & Permissions" };

export default function RolesSettingsPage() {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-semibold">Roles &amp; Permissions</h2>
        <p className="text-muted-foreground text-sm">
          Roles decide what members can do. The backend enforces every permission on each
          request — these settings control access, not just the interface.
        </p>
      </div>

      <RequirePermission
        permission={PERM.ROLE_READ}
        fallback={<NoAccessState action="view roles and permissions" />}
      >
        <RolesView />
      </RequirePermission>
    </div>
  );
}
