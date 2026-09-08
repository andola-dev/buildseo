import type { Metadata } from "next";
import { Suspense } from "react";

import { TableSkeleton } from "@/components/feedback/loading-state";
import { NoAccessState } from "@/components/feedback/no-access-state";
import { PageHeader } from "@/components/shared/page-header";
import { RequirePermission } from "@/components/shared/permission-gate";
import { PERM } from "@/config/permissions";
import { AuditTable } from "@/features/audit/components/audit-table";

export const metadata: Metadata = { title: "Audit Logs" };

export default function AuditPage() {
  return (
    <>
      <PageHeader
        title="Audit Logs"
        description="Every security and business event recorded in this workspace."
      />

      <RequirePermission
        permission={PERM.AUDIT_READ}
        fallback={<NoAccessState action="read the audit trail" />}
      >
        <Suspense fallback={<TableSkeleton columns={6} />}>
          <AuditTable />
        </Suspense>
      </RequirePermission>
    </>
  );
}
