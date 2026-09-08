import type { Metadata } from "next";
import { Suspense } from "react";

import { TableSkeleton } from "@/components/feedback/loading-state";
import { FreeListingsBadge } from "@/components/shared/free-listings-badge";
import { PageHeader } from "@/components/shared/page-header";
import { OpportunitiesTable } from "@/features/opportunities/components/opportunities-table";

export const metadata: Metadata = { title: "Opportunities" };

export default function OpportunitiesPage() {
  return (
    <>
      <PageHeader
        title="Opportunities"
        description="Qualified publishers paired with a campaign. Approve the ones worth submitting to."
        badges={<FreeListingsBadge />}
      />

      <Suspense fallback={<TableSkeleton columns={9} />}>
        <OpportunitiesTable />
      </Suspense>
    </>
  );
}
