import type { Metadata } from "next";

import { SecuritySettings } from "@/features/settings/components/security-settings";

export const metadata: Metadata = { title: "Security" };

export default function SecuritySettingsPage() {
  return <SecuritySettings />;
}
