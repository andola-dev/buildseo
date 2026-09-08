import { PageHeader } from "@/components/shared/page-header";
import { SettingsNav } from "@/components/layout/settings-nav";

/** Settings shell: one header plus the section rail (spec §31). */
export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <PageHeader
        title="Settings"
        description="Workspace configuration, team access and provider credentials."
      />

      <div className="flex flex-col gap-6 lg:flex-row lg:gap-10">
        <SettingsNav />
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </>
  );
}
