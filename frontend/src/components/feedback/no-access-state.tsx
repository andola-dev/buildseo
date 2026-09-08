import { ShieldOff } from "lucide-react";

import { EmptyState } from "@/components/feedback/empty-state";

/**
 * Shown when the user lacks the permission a page needs (spec §35).
 *
 * A clear explanation beats a blank screen or a wall of 403 errors. This is
 * only about what the interface offers — the backend refuses the request
 * regardless of what is rendered here.
 */
export function NoAccessState({ action }: { action: string }) {
  return (
    <div className="rounded-lg border">
      <EmptyState
        icon={ShieldOff}
        title="You don't have access"
        description={`Your role in this workspace doesn't allow you to ${action}. Ask a workspace owner or admin if you need it.`}
      />
    </div>
  );
}
