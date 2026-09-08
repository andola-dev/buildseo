import type { Metadata } from "next";
import { Suspense } from "react";
import Link from "next/link";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { TableSkeleton } from "@/components/feedback/loading-state";
import { PageHeader } from "@/components/shared/page-header";
import { PermissionGate } from "@/components/shared/permission-gate";
import { PERM } from "@/config/permissions";
import { WebsitesTable } from "@/features/websites/components/websites-table";

export const metadata: Metadata = { title: "Client Websites" };

export default function WebsitesPage() {
  return (
    <>
      <PageHeader
        title="Client Websites"
        description="The sites this workspace builds free directory and listing links for."
        actions={
          <PermissionGate permission={PERM.CLIENT_WEBSITE_CREATE}>
            <Button asChild size="sm">
              <Link href="/websites/new">
                <Plus className="size-4" aria-hidden />
                Add website
              </Link>
            </Button>
          </PermissionGate>
        }
      />

      {/* The table reads its filters from the URL, so it needs a Suspense
          boundary around `useSearchParams`. */}
      <Suspense fallback={<TableSkeleton />}>
        <WebsitesTable />
      </Suspense>
    </>
  );
}
