import type { Metadata } from "next";
import { Suspense } from "react";

import { FormSkeleton } from "@/components/feedback/loading-state";
import { NoAccessState } from "@/components/feedback/no-access-state";
import { PageHeader } from "@/components/shared/page-header";
import { RequirePermission } from "@/components/shared/permission-gate";
import { PERM } from "@/config/permissions";
import { CampaignWizard } from "@/features/campaigns/components/campaign-wizard";

export const metadata: Metadata = { title: "New campaign" };

export default function NewCampaignPage() {
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="New campaign"
        description="Set up a free listing campaign for one of your client websites."
      />

      <RequirePermission
        permission={PERM.CAMPAIGN_CREATE}
        fallback={<NoAccessState action="create campaigns" />}
      >
        <Suspense fallback={<FormSkeleton />}>
          <CampaignWizard />
        </Suspense>
      </RequirePermission>
    </div>
  );
}
