import type { Metadata } from "next";

import { GeneralSettings } from "@/features/settings/components/general-settings";

export const metadata: Metadata = { title: "General" };

export default function GeneralSettingsPage() {
  return <GeneralSettings />;
}
