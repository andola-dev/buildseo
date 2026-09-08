import type { Metadata } from "next";
import { Suspense } from "react";

import { TableSkeleton } from "@/components/feedback/loading-state";
import { PageHeader } from "@/components/shared/page-header";
import { SubmissionsTable } from "@/features/submissions/components/submissions-table";

export const metadata: Metadata = { title: "Submissions" };

export default function SubmissionsPage() {
  return (
    <>
      <PageHeader
        title="Submissions"
        description="Review, approve and verify free listing submissions."
      />

      <Suspense fallback={<TableSkeleton columns={7} />}>
        <SubmissionsTable />
      </Suspense>
    </>
  );
}
