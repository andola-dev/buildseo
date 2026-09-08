import type { Metadata } from "next";

import { ProfileSettings } from "@/features/settings/components/profile-settings";

export const metadata: Metadata = { title: "Profile" };

export default function ProfileSettingsPage() {
  return <ProfileSettings />;
}
