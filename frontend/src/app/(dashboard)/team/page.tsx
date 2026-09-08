import type { Metadata } from "next";
import { Suspense } from "react";
import Link from "next/link";
import { Shield } from "lucide-react";

import { Button } from "@/components/ui/button";
import { TableSkeleton } from "@/components/feedback/loading-state";
import { NoAccessState } from "@/components/feedback/no-access-state";
import { PageHeader } from "@/components/shared/page-header";
import { PermissionGate, RequirePermission } from "@/components/shared/permission-gate";
import { PERM } from "@/config/permissions";
import { TeamTable } from "@/features/team/components/team-table";

export const metadata: Metadata = { title: "Team" };

export default function TeamPage() {
  return (
    <>
      <PageHeader
        title="Team"
        description="Who has access to this workspace, and what they can do."
        actions={
          <PermissionGate permission={PERM.ROLE_READ}>
            <Button asChild variant="outline" size="sm">
              <Link href="/settings/roles">
                <Shield className="size-4" aria-hidden />
                Roles &amp; permissions
              </Link>
            </Button>
          </PermissionGate>
        }
      />

      <RequirePermission
        permission={PERM.USER_READ}
        fallback={<NoAccessState action="view workspace members" />}
      >
        <Suspense fallback={<TableSkeleton columns={5} />}>
          <TeamTable />
        </Suspense>
      </RequirePermission>
    </>
  );
}
