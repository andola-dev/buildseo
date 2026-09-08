import Link from "next/link";
import { FileQuestion } from "lucide-react";

import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="flex min-h-dvh items-center justify-center p-6">
      <div className="flex max-w-sm flex-col items-center gap-4 text-center">
        <div className="bg-muted text-muted-foreground flex size-10 items-center justify-center rounded-lg">
          <FileQuestion className="size-5" aria-hidden />
        </div>
        <div className="space-y-1">
          <h1 className="text-lg font-semibold">Page not found</h1>
          <p className="text-muted-foreground text-sm">
            The page you were looking for doesn&apos;t exist or has moved.
          </p>
        </div>
        <Button asChild size="sm">
          <Link href="/dashboard">Back to dashboard</Link>
        </Button>
      </div>
    </main>
  );
}
