import type { Metadata } from "next";

import { NoAccessState } from "@/components/feedback/no-access-state";
import { RequirePermission } from "@/components/shared/permission-gate";
import { PERM } from "@/config/permissions";
import { AiSettings } from "@/features/credentials/components/ai-settings";

export const metadata: Metadata = { title: "AI Providers" };

export default function AiSettingsPage() {
  return (
    <RequirePermission
      permission={PERM.CREDENTIAL_READ}
      fallback={<NoAccessState action="view provider credentials" />}
    >
      <AiSettings />
    </RequirePermission>
  );
}
