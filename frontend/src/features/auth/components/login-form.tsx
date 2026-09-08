"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertCircle, Link2, WifiOff } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { APP_NAME } from "@/config/app";
import { fieldErrorMap, isApiError } from "@/lib/api/errors";
import { useAuth } from "@/lib/auth/auth-provider";
import { loginSchema } from "@/lib/validation/schemas";
import { cn } from "@/lib/utils/cn";

type FormState = "idle" | "submitting" | "success" | "error";

interface FormError {
  kind: "auth" | "network" | "other";
  message: string;
}

/**
 * Sign-in form (spec §11).
 *
 * States: idle, submitting, success, authentication error, network error.
 * Authentication failures deliberately do not distinguish "no such account"
 * from "wrong password" — that distinction would let an attacker enumerate
 * accounts, and the backend does not make it either.
 *
 * Password reset and email verification are out of scope for the MVP
 * (spec §11/§72), so no such links are offered.
 */
export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);

  const [state, setState] = useState<FormState>("idle");
  const [formError, setFormError] = useState<FormError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  /**
   * Where to go after signing in.
   *
   * Only same-origin relative paths are honoured, so a crafted
   * `?next=https://evil.example` cannot turn the login page into an open
   * redirect.
   */
  function safeNextPath(): string {
    const next = searchParams.get("next");
    if (!next || !next.startsWith("/") || next.startsWith("//")) return "/dashboard";
    return next;
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setFormError(null);
    setFieldErrors({});

    const parsed = loginSchema.safeParse({ email, password, remember });
    if (!parsed.success) {
      const errors: Record<string, string> = {};
      for (const issue of parsed.error.issues) {
        const field = issue.path[0];
        if (typeof field === "string" && !(field in errors)) {
          errors[field] = issue.message;
        }
      }
      setFieldErrors(errors);
      setState("error");
      return;
    }

    setState("submitting");

    try {
      await login({
        email: parsed.data.email,
        password: parsed.data.password,
        remember: parsed.data.remember,
      });

      setState("success");
      router.replace(safeNextPath());
    } catch (error) {
      setState("error");

      if (isApiError(error)) {
        setFieldErrors(fieldErrorMap(error));

        if (error.isConnectivityError) {
          setFormError({ kind: "network", message: error.message });
          return;
        }

        setFormError({
          kind: error.isUnauthorized || error.status === 403 ? "auth" : "other",
          message: error.message,
        });
        return;
      }

      setFormError({
        kind: "other",
        message: "Unable to sign in. Please try again.",
      });
    }
  }

  const submitting = state === "submitting" || state === "success";

  return (
    <div className="w-full max-w-sm">
      <div className="mb-8 flex flex-col items-center gap-3 text-center">
        <span className="bg-primary text-primary-foreground flex size-9 items-center justify-center rounded-lg">
          <Link2 className="size-4.5" aria-hidden />
        </span>
        <div className="space-y-1">
          <h1 className="text-lg font-semibold tracking-tight">Sign in to {APP_NAME}</h1>
          <p className="text-muted-foreground text-sm">
            Free listing and directory link building for SEO teams.
          </p>
        </div>
      </div>

      {formError ? (
        <Alert
          variant={formError.kind === "network" ? "warning" : "destructive"}
          className="mb-5"
        >
          {formError.kind === "network" ? (
            <WifiOff aria-hidden />
          ) : (
            <AlertCircle aria-hidden />
          )}
          <AlertTitle>
            {formError.kind === "network" ? "Can't reach the server" : "Sign-in failed"}
          </AlertTitle>
          <AlertDescription>{formError.message}</AlertDescription>
        </Alert>
      ) : null}

      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            autoFocus
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            disabled={submitting}
            aria-invalid={Boolean(fieldErrors.email)}
            aria-describedby={fieldErrors.email ? "email-error" : undefined}
            placeholder="you@company.com"
          />
          {fieldErrors.email ? (
            <p id="email-error" className="text-destructive text-xs">
              {fieldErrors.email}
            </p>
          ) : null}
        </div>

        <div className="space-y-2">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            disabled={submitting}
            aria-invalid={Boolean(fieldErrors.password)}
            aria-describedby={fieldErrors.password ? "password-error" : undefined}
          />
          {fieldErrors.password ? (
            <p id="password-error" className="text-destructive text-xs">
              {fieldErrors.password}
            </p>
          ) : null}
        </div>

        <div className="flex items-center gap-2 pt-1">
          <Checkbox
            id="remember"
            checked={remember}
            onCheckedChange={(checked) => setRemember(checked === true)}
            disabled={submitting}
          />
          <Label htmlFor="remember" className="text-muted-foreground font-normal">
            Remember this session
          </Label>
        </div>

        <Button type="submit" className="w-full" loading={submitting}>
          {state === "success" ? "Signing in…" : submitting ? "Signing in…" : "Sign in"}
        </Button>

        {/* Announce state changes for screen-reader users (spec §44). */}
        <p aria-live="polite" className={cn("sr-only")}>
          {state === "submitting"
            ? "Signing in"
            : state === "success"
              ? "Signed in, redirecting"
              : state === "error"
                ? (formError?.message ?? "There is a problem with the form")
                : ""}
        </p>
      </form>

      <p className="text-muted-foreground mt-8 text-center text-xs">
        Need an account? Ask your workspace owner to invite you, or{" "}
        <Link href="/register" className="text-foreground underline underline-offset-4">
          create a workspace
        </Link>
        .
      </p>
    </div>
  );
}
