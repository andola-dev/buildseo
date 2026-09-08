import { Check, Circle, Loader2, X } from "lucide-react";

import { cn } from "@/lib/utils/cn";
import type { SubmissionStatus } from "@/types/api";

/**
 * The happy path a submission travels (spec §30).
 *
 * Failure states (REJECTED, FAILED) are not stages — they end the journey, and
 * the caller renders them as an alert instead of a step.
 */
const STAGES: { status: SubmissionStatus; label: string }[] = [
  { status: "READY", label: "Ready" },
  { status: "PENDING_APPROVAL", label: "Pending approval" },
  { status: "SUBMITTED", label: "Submitted" },
  { status: "VERIFICATION_PENDING", label: "Verification pending" },
  { status: "PUBLISHED", label: "Published" },
  { status: "VERIFIED", label: "Verified" },
];

const TERMINAL_FAILURES: SubmissionStatus[] = ["REJECTED", "FAILED"];

/** Progress through the submission lifecycle. */
export function VerificationTimeline({ status }: { status: string }) {
  const failed = TERMINAL_FAILURES.includes(status as SubmissionStatus);
  const currentIndex = STAGES.findIndex((stage) => stage.status === status);

  return (
    <ol className="space-y-0" aria-label="Submission progress">
      {STAGES.map((stage, index) => {
        // With an unknown or failed status nothing is marked complete, so the
        // timeline never claims progress the record doesn't show.
        const done = !failed && currentIndex >= 0 && index < currentIndex;
        const active = !failed && index === currentIndex;

        const Icon = done ? Check : active ? Loader2 : Circle;

        return (
          <li key={stage.status} className="flex gap-3">
            <div className="flex flex-col items-center">
              <span
                className={cn(
                  "flex size-6 shrink-0 items-center justify-center rounded-full border",
                  done && "bg-success/12 border-success/40 text-success",
                  active && "bg-primary/10 border-primary text-primary",
                  !done && !active && "bg-muted text-muted-foreground border-transparent",
                )}
              >
                <Icon
                  className={cn("size-3", active && stage.status !== "VERIFIED" && "animate-spin")}
                  aria-hidden
                />
              </span>
              {index < STAGES.length - 1 ? (
                <span
                  className={cn("my-0.5 w-px flex-1", done ? "bg-success/40" : "bg-border")}
                  aria-hidden
                />
              ) : null}
            </div>

            <div className="pb-4">
              <div
                className={cn(
                  "text-sm",
                  active ? "font-medium" : done ? "" : "text-muted-foreground",
                )}
              >
                {stage.label}
              </div>
              {active ? (
                <div className="text-muted-foreground text-xs">Current stage</div>
              ) : null}
            </div>
          </li>
        );
      })}

      {failed ? (
        <li className="flex gap-3">
          <span className="bg-destructive/12 text-destructive flex size-6 shrink-0 items-center justify-center rounded-full">
            <X className="size-3" aria-hidden />
          </span>
          <div className="text-destructive text-sm font-medium">
            {status === "REJECTED" ? "Rejected" : "Failed"}
          </div>
        </li>
      ) : null}
    </ol>
  );
}
