import { BadgeCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils/cn";

/**
 * Makes the product's scope explicit in the interface (spec §21/§73).
 *
 * The MVP works with free directory and listing links only. Surfacing that
 * where campaigns and opportunities are created is what stops a user expecting
 * paid placements, guest posts or outreach — none of which exist here.
 */
export function FreeListingsBadge({ className }: { className?: string }) {
  return (
    <Badge variant="success" className={cn("uppercase", className)}>
      <BadgeCheck className="size-3" aria-hidden />
      Free listings only
    </Badge>
  );
}
