import type { Metadata } from "next";

import { WorkspaceSettings } from "@/features/settings/components/workspace-settings";

export const metadata: Metadata = { title: "Workspace" };

export default function WorkspaceSettingsPage() {
  return <WorkspaceSettings />;
}
