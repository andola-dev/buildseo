"use client";

import { useEffect } from "react";
import { AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";

/**
 * The last-resort error boundary.
 *
 * Query failures are handled per screen with `ErrorState`; this catches render
 * faults. The message is generic on purpose — a stack trace must not reach the
 * user (spec §11/§39).
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Unhandled application error", error);
  }, [error]);

  return (
    <main className="flex min-h-dvh items-center justify-center p-6">
      <div className="flex max-w-sm flex-col items-center gap-4 text-center">
        <div className="bg-destructive/10 text-destructive flex size-10 items-center justify-center rounded-lg">
          <AlertTriangle className="size-5" aria-hidden />
        </div>
        <div className="space-y-1">
          <h1 className="text-lg font-semibold">Something went wrong</h1>
          <p className="text-muted-foreground text-sm">
            An unexpected error occurred. Try again, or reload the page.
          </p>
        </div>
        <Button size="sm" onClick={reset}>
          Try again
        </Button>
      </div>
    </main>
  );
}
