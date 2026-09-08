import type { Metadata } from "next";
import { Suspense } from "react";
import Link from "next/link";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { TableSkeleton } from "@/components/feedback/loading-state";
import { FreeListingsBadge } from "@/components/shared/free-listings-badge";
import { PageHeader } from "@/components/shared/page-header";
import { PermissionGate } from "@/components/shared/permission-gate";
import { PERM } from "@/config/permissions";
import { CampaignsTable } from "@/features/campaigns/components/campaigns-table";

export const metadata: Metadata = { title: "Campaigns" };

export default function CampaignsPage() {
  return (
    <>
      <PageHeader
        title="Campaigns"
        description="Link-building campaigns for your client websites."
        badges={<FreeListingsBadge />}
        actions={
          <PermissionGate permission={PERM.CAMPAIGN_CREATE}>
            <Button asChild size="sm">
              <Link href="/campaigns/new">
                <Plus className="size-4" aria-hidden />
                New campaign
              </Link>
            </Button>
          </PermissionGate>
        }
      />

      <Suspense fallback={<TableSkeleton />}>
        <CampaignsTable />
      </Suspense>
    </>
  );
}
