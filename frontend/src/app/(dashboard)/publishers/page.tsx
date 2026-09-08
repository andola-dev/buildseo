import type { Metadata } from "next";
import { Suspense } from "react";
import Link from "next/link";
import { Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { TableSkeleton } from "@/components/feedback/loading-state";
import { FreeListingsBadge } from "@/components/shared/free-listings-badge";
import { PageHeader } from "@/components/shared/page-header";
import { PermissionGate } from "@/components/shared/permission-gate";
import { PERM } from "@/config/permissions";
import { PublishersTable } from "@/features/publishers/components/publishers-table";

export const metadata: Metadata = { title: "Publishers" };

export default function PublishersPage() {
  return (
    <>
      <PageHeader
        title="Publisher Database"
        description="Free directories and listing sites, with their qualification scores."
        badges={<FreeListingsBadge />}
        actions={
          <PermissionGate permission={PERM.PUBLISHER_DISCOVER}>
            <Button asChild size="sm">
              <Link href="/publishers/discovery">
                <Search className="size-4" aria-hidden />
                Discovery
              </Link>
            </Button>
          </PermissionGate>
        }
      />

      <Suspense fallback={<TableSkeleton columns={10} />}>
        <PublishersTable />
      </Suspense>
    </>
  );
}
