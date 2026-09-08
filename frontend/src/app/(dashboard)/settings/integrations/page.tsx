import type { Metadata } from "next";

import { NoAccessState } from "@/components/feedback/no-access-state";
import { RequirePermission } from "@/components/shared/permission-gate";
import { PERM } from "@/config/permissions";
import { IntegrationSettings } from "@/features/credentials/components/integration-settings";

export const metadata: Metadata = { title: "Integrations" };

export default function IntegrationsSettingsPage() {
  return (
    <RequirePermission
      permission={PERM.CREDENTIAL_READ}
      fallback={<NoAccessState action="view integration credentials" />}
    >
      <IntegrationSettings />
    </RequirePermission>
  );
}
