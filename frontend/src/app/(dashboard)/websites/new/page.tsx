import type { Metadata } from "next";

import { PageHeader } from "@/components/shared/page-header";
import { RequirePermission } from "@/components/shared/permission-gate";
import { NoAccessState } from "@/components/feedback/no-access-state";
import { PERM } from "@/config/permissions";
import { WebsiteForm } from "@/features/websites/components/website-form";

export const metadata: Metadata = { title: "Add client website" };

export default function NewWebsitePage() {
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Add client website"
        description="Add the site you're building links to. You can create campaigns for it next."
      />

      <RequirePermission
        permission={PERM.CLIENT_WEBSITE_CREATE}
        fallback={<NoAccessState action="add client websites" />}
      >
        <WebsiteForm />
      </RequirePermission>
    </div>
  );
}
