"use client";

import { useState } from "react";
import Link from "next/link";
import { LogOut, Settings, SlidersHorizontal, User } from "lucide-react";
import { toast } from "sonner";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { errorMessage } from "@/lib/api/errors";
import { useAuth } from "@/lib/auth/auth-provider";
import { initials, userDisplayName } from "@/lib/utils/format";
import { cn } from "@/lib/utils/cn";

/** Account menu (spec §10). */
export function UserMenu({ compact = false }: { compact?: boolean }) {
  const { user, logout } = useAuth();
  const [signingOut, setSigningOut] = useState(false);

  const name = userDisplayName(user);

  async function handleLogout() {
    setSigningOut(true);
    try {
      await logout();
    } catch (error) {
      // `logout` clears the token and redirects in a `finally`, so this device
      // *is* signed out — only the server-side revocation failed. Saying
      // "couldn't sign out" over an already-empty session would be wrong.
      toast.warning("Signed out on this device only", {
        description: `${errorMessage(error)} Other sessions may still be active.`,
      });
    } finally {
      setSigningOut(false);
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size={compact ? "icon" : "default"}
          className={cn(!compact && "gap-2 px-2")}
          aria-label={`Account menu for ${name}`}
        >
          <Avatar className="size-7">
            <AvatarFallback>{initials(name, user?.email)}</AvatarFallback>
          </Avatar>
          {compact ? null : (
            <span className="hidden max-w-32 truncate text-sm lg:inline">{name}</span>
          )}
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="text-foreground">
          <div className="truncate text-sm font-medium">{name}</div>
          <div className="text-muted-foreground truncate text-xs font-normal">
            {user?.email}
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />

        <DropdownMenuItem asChild>
          <Link href="/settings/profile">
            <User className="size-4" aria-hidden />
            Profile
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/settings/general">
            <SlidersHorizontal className="size-4" aria-hidden />
            Preferences
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/settings">
            <Settings className="size-4" aria-hidden />
            Settings
          </Link>
        </DropdownMenuItem>

        <DropdownMenuSeparator />
        <DropdownMenuItem
          variant="destructive"
          disabled={signingOut}
          onSelect={(event) => {
            // Keep the menu mounted while the request is in flight so the
            // disabled state is visible instead of the menu vanishing.
            event.preventDefault();
            void handleLogout();
          }}
        >
          <LogOut className="size-4" aria-hidden />
          {signingOut ? "Signing out…" : "Log out"}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
