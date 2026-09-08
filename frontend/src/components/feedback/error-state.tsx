"use client";

import { AlertTriangle, RefreshCw, ShieldOff, SearchX, WifiOff } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { isApiError } from "@/lib/api/errors";
import { cn } from "@/lib/utils/cn";

interface ErrorStateProps {
  /** The thrown value. `ApiError` gets tailored copy and iconography. */
  error: unknown;
  /** What failed to load, e.g. "your publishers" (spec §39). */
  resource?: string;
  onRetry?: () => void;
  className?: string;
}

interface Presentation {
  icon: LucideIcon;
  title: string;
  description: string;
  /** Retrying a 403 or 404 will not help. */
  retryable: boolean;
}

function presentation(error: unknown, resource?: string): Presentation {
  const subject = resource ? `load ${resource}` : "complete that request";

  if (!isApiError(error)) {
    return {
      icon: AlertTriangle,
      title: "Something went wrong",
      description: `We couldn't ${subject}.`,
      retryable: true,
    };
  }

  if (error.isConnectivityError) {
    return {
      icon: WifiOff,
      title: "Can't reach the server",
      description: error.message,
      retryable: true,
    };
  }

  if (error.isForbidden) {
    return {
      icon: ShieldOff,
      title: "You don't have access",
      description: error.message,
      retryable: false,
    };
  }

  if (error.isNotFound) {
    return {
      icon: SearchX,
      title: "Not found",
      description: error.message,
      retryable: false,
    };
  }

  return {
    icon: AlertTriangle,
    title: "Something went wrong",
    description: error.message,
    retryable: error.isRetryable,
  };
}

/** The reusable error panel for any failed query (spec §39). */
export function ErrorState({ error, resource, onRetry, className }: ErrorStateProps) {
  const { icon: Icon, title, description, retryable } = presentation(error, resource);

  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center gap-3 px-6 py-14 text-center",
        className,
      )}
    >
      <div className="bg-destructive/10 text-destructive flex size-10 items-center justify-center rounded-lg">
        <Icon className="size-5" aria-hidden />
      </div>

      <div className="space-y-1">
        <h3 className="text-sm font-semibold">{title}</h3>
        <p className="text-muted-foreground mx-auto max-w-sm text-sm">{description}</p>
      </div>

      {onRetry && retryable ? (
        <Button variant="outline" size="sm" onClick={onRetry} className="mt-1">
          <RefreshCw className="size-4" aria-hidden />
          Try again
        </Button>
      ) : null}
    </div>
  );
}
