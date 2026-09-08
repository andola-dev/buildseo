"use client";

import { useState } from "react";
import Link from "next/link";
import { AlertCircle, Link2, WifiOff } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Field, fieldAria } from "@/components/forms/field";
import { APP_NAME } from "@/config/app";
import { authApi } from "@/lib/api";
import { isApiError } from "@/lib/api/errors";
import { PASSWORD_MIN_LENGTH, registerSchema } from "@/lib/validation/schemas";
import { useFormErrors } from "@/lib/validation/use-form-errors";

type FormState = "idle" | "submitting" | "success" | "error";

/**
 * Create an account and its first workspace (`POST /auth/register`).
 *
 * A workspace name is required rather than optional: the backend only creates
 * one when a name is supplied, and an account with no workspace cannot use any
 * tenant-scoped endpoint — so registering without one would land the user on a
 * dead end.
 *
 * Registration signs the user in, so it goes through the same session proxy as
 * login and the refresh token never reaches the browser. No email is sent and
 * no address is verified, matching the MVP scope.
 */
export function RegisterForm() {
  const { fieldError, formError, setFormError, validate, applyServerError } = useFormErrors();

  const [email, setEmail] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [workspaceName, setWorkspaceName] = useState("");
  const [remember, setRemember] = useState(true);

  const [state, setState] = useState<FormState>("idle");
  const [networkError, setNetworkError] = useState(false);

  /** Clear the passwords; they must not linger in component state. */
  function wipePasswords() {
    setPassword("");
    setConfirmPassword("");
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setFormError(null);
    setNetworkError(false);

    const values = validate(registerSchema, {
      email,
      first_name: firstName,
      last_name: lastName,
      password,
      confirm_password: confirmPassword,
      workspace_name: workspaceName,
      remember,
    });
    if (!values) {
      setState("error");
      return;
    }

    setState("submitting");

    try {
      await authApi.register({
        email: values.email,
        password: values.password,
        ...(values.first_name ? { firstName: values.first_name } : {}),
        ...(values.last_name ? { lastName: values.last_name } : {}),
        workspaceName: values.workspace_name,
        remember: values.remember,
      });

      setState("success");
      wipePasswords();
      // A full navigation, so the provider bootstraps from the fresh cookie
      // rather than inheriting this page's pre-registration session state.
      window.location.assign("/dashboard");
    } catch (error) {
      setState("error");
      wipePasswords();

      if (isApiError(error) && error.isConnectivityError) {
        setNetworkError(true);
        setFormError(error.message);
        return;
      }

      applyServerError(error);
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
          <h1 className="text-lg font-semibold tracking-tight">Create your {APP_NAME} workspace</h1>
          <p className="text-muted-foreground text-sm">
            Free listing and directory link building for SEO teams.
          </p>
        </div>
      </div>

      {formError ? (
        <Alert variant={networkError ? "warning" : "destructive"} className="mb-5">
          {networkError ? <WifiOff aria-hidden /> : <AlertCircle aria-hidden />}
          <AlertTitle>
            {networkError ? "Can't reach the server" : "Couldn't create your account"}
          </AlertTitle>
          <AlertDescription>{formError}</AlertDescription>
        </Alert>
      ) : null}

      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <Field id="register-workspace" label="Workspace name" required error={fieldError("workspace_name")}>
          <Input
            {...fieldAria("register-workspace", { error: fieldError("workspace_name") })}
            value={workspaceName}
            onChange={(event) => setWorkspaceName(event.target.value)}
            placeholder="Acme Marketing"
            autoFocus
            disabled={submitting}
          />
        </Field>

        <Field id="register-email" label="Email" required error={fieldError("email")}>
          <Input
            {...fieldAria("register-email", { error: fieldError("email") })}
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@company.com"
            disabled={submitting}
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field id="register-first-name" label="First name" error={fieldError("first_name")}>
            <Input
              {...fieldAria("register-first-name", { error: fieldError("first_name") })}
              autoComplete="given-name"
              value={firstName}
              onChange={(event) => setFirstName(event.target.value)}
              disabled={submitting}
            />
          </Field>

          <Field id="register-last-name" label="Last name" error={fieldError("last_name")}>
            <Input
              {...fieldAria("register-last-name", { error: fieldError("last_name") })}
              autoComplete="family-name"
              value={lastName}
              onChange={(event) => setLastName(event.target.value)}
              disabled={submitting}
            />
          </Field>
        </div>

        <Field
          id="register-password"
          label="Password"
          required
          error={fieldError("password")}
          hint={`At least ${PASSWORD_MIN_LENGTH} characters.`}
        >
          <Input
            {...fieldAria("register-password", {
              error: fieldError("password"),
              hint: `At least ${PASSWORD_MIN_LENGTH} characters.`,
            })}
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            disabled={submitting}
          />
        </Field>

        <Field
          id="register-confirm"
          label="Confirm password"
          required
          error={fieldError("confirm_password")}
        >
          <Input
            {...fieldAria("register-confirm", { error: fieldError("confirm_password") })}
            type="password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            disabled={submitting}
          />
        </Field>

        <div className="flex items-center gap-2 pt-1">
          <Checkbox
            id="register-remember"
            checked={remember}
            onCheckedChange={(checked) => setRemember(checked === true)}
            disabled={submitting}
          />
          <Label htmlFor="register-remember" className="text-muted-foreground font-normal">
            Remember this session
          </Label>
        </div>

        <Button type="submit" className="w-full" loading={submitting}>
          {submitting ? "Creating your workspace…" : "Create workspace"}
        </Button>

        <p aria-live="polite" className="sr-only">
          {state === "submitting"
            ? "Creating your account"
            : state === "success"
              ? "Account created, redirecting"
              : state === "error"
                ? (formError ?? "There is a problem with the form")
                : ""}
        </p>
      </form>

      <p className="text-muted-foreground mt-8 text-center text-xs">
        Already have an account?{" "}
        <Link href="/login" className="text-foreground underline underline-offset-4">
          Sign in
        </Link>
        .
      </p>
    </div>
  );
}
