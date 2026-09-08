import type { Metadata } from "next";
import { Suspense } from "react";

import { LoadingState } from "@/components/feedback/loading-state";
import { NoAccessState } from "@/components/feedback/no-access-state";
import { PageHeader } from "@/components/shared/page-header";
import { RequirePermission } from "@/components/shared/permission-gate";
import { PERM } from "@/config/permissions";
import { DiscoveryPanel } from "@/features/publishers/components/discovery-panel";

export const metadata: Metadata = { title: "Publisher discovery" };

export default function DiscoveryPage() {
  return (
    <>
      <PageHeader
        title="Discovery"
        description="Find free directories and listing sites that match your client's industry and market. Discovery runs in the background."
      />

      <RequirePermission
        permission={PERM.PUBLISHER_DISCOVER}
        fallback={<NoAccessState action="run publisher discovery" />}
      >
        <Suspense fallback={<LoadingState label="Loading discovery" />}>
          <DiscoveryPanel />
        </Suspense>
      </RequirePermission>
    </>
  );
}
