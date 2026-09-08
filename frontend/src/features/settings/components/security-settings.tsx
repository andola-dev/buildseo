"use client";

import { useState } from "react";
import { Laptop, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/feedback/confirm-dialog";
import { ErrorState } from "@/components/feedback/error-state";
import { Field, fieldAria } from "@/components/forms/field";
import { authApi, meApi } from "@/lib/api";
import { errorMessage } from "@/lib/api/errors";
import { queryKeys } from "@/lib/query/keys";
import { PASSWORD_MIN_LENGTH, passwordChangeSchema } from "@/lib/validation/schemas";
import { useFormErrors } from "@/lib/validation/use-form-errors";
import { formatDateTime, truncate } from "@/lib/utils/format";
import type { UserSession } from "@/types/api";

/** Password change and session management (spec §31). */
export function SecuritySettings() {
  const queryClient = useQueryClient();
  const { fieldError, formError, validate, applyServerError, clear } = useFormErrors();

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [revokeOthers, setRevokeOthers] = useState(true);
  const [pendingRevoke, setPendingRevoke] = useState<UserSession | null>(null);

  const sessions = useQuery({
    queryKey: queryKeys.security.sessions(),
    queryFn: authApi.listSessions,
  });

  const changePassword = useMutation({ mutationFn: meApi.changePassword });

  const revokeSession = useMutation({
    mutationFn: authApi.revokeSession,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.security.sessions() });
    },
  });

  /** Clear the password fields; they must not linger in component state. */
  function wipePasswords() {
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    const values = validate(passwordChangeSchema, {
      current_password: currentPassword,
      new_password: newPassword,
      confirm_password: confirmPassword,
      revoke_other_sessions: revokeOthers,
    });
    if (!values) return;

    try {
      await changePassword.mutateAsync({
        current_password: values.current_password,
        new_password: values.new_password,
        revoke_other_sessions: values.revoke_other_sessions,
      });
      toast.success("Password changed", {
        description: values.revoke_other_sessions
          ? "Your other sessions have been signed out."
          : undefined,
      });
      wipePasswords();
      clear();
      await queryClient.invalidateQueries({ queryKey: queryKeys.security.sessions() });
    } catch (error) {
      applyServerError(error);
    } finally {
      // Never leave the plaintext passwords in state after a submit attempt.
      wipePasswords();
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-semibold">Security</h2>
        <p className="text-muted-foreground text-sm">
          Your password and the devices signed in to your account.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Change password</CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          <form onSubmit={handleSubmit} noValidate className="max-w-md space-y-4">
            {formError ? (
              <Alert variant="destructive">
                <AlertDescription>{formError}</AlertDescription>
              </Alert>
            ) : null}

            <Field
              id="current-password"
              label="Current password"
              required
              error={fieldError("current_password")}
            >
              <Input
                {...fieldAria("current-password", {
                  error: fieldError("current_password"),
                })}
                type="password"
                autoComplete="current-password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
              />
            </Field>

            <Field
              id="new-password"
              label="New password"
              required
              error={fieldError("new_password")}
              hint={`At least ${PASSWORD_MIN_LENGTH} characters.`}
            >
              <Input
                {...fieldAria("new-password", {
                  error: fieldError("new_password"),
                  hint: `At least ${PASSWORD_MIN_LENGTH} characters.`,
                })}
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
              />
            </Field>

            <Field
              id="confirm-password"
              label="Confirm new password"
              required
              error={fieldError("confirm_password")}
            >
              <Input
                {...fieldAria("confirm-password", {
                  error: fieldError("confirm_password"),
                })}
                type="password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
              />
            </Field>

            <div className="flex items-start gap-2">
              <Checkbox
                id="revoke-others"
                checked={revokeOthers}
                onCheckedChange={(checked) => setRevokeOthers(checked === true)}
              />
              <Label htmlFor="revoke-others" className="font-normal">
                Sign out my other sessions
              </Label>
            </div>

            <Button type="submit" size="sm" loading={changePassword.isPending}>
              Change password
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Active sessions</CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          {sessions.isPending ? (
            <div className="space-y-2" aria-hidden>
              {Array.from({ length: 2 }).map((_, index) => (
                <Skeleton key={index} className="h-12 w-full" />
              ))}
            </div>
          ) : sessions.error ? (
            <ErrorState
              error={sessions.error}
              resource="your active sessions"
              onRetry={() => void sessions.refetch()}
            />
          ) : (
            <ul className="divide-y">
              {sessions.data?.map((session) => (
                <li key={session.id} className="flex items-center gap-3 py-3 first:pt-0">
                  <span className="bg-muted text-muted-foreground flex size-8 shrink-0 items-center justify-center rounded-md">
                    <Laptop className="size-4" aria-hidden />
                  </span>

                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm">
                        {session.user_agent ? truncate(session.user_agent, 40) : "Unknown device"}
                      </span>
                      {session.is_current ? (
                        <Badge variant="info">This device</Badge>
                      ) : null}
                    </div>
                    <div className="text-muted-foreground flex flex-wrap gap-x-3 text-xs">
                      <span className="tabular">{session.ip_address ?? "Unknown IP"}</span>
                      <span>Started {formatDateTime(session.created_at)}</span>
                      {session.last_used_at ? (
                        <span>Last used {formatDateTime(session.last_used_at)}</span>
                      ) : null}
                    </div>
                  </div>

                  {session.is_current ? null : (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setPendingRevoke(session)}
                    >
                      Sign out
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Alert variant="info">
        <ShieldCheck aria-hidden />
        <AlertTitle>How your session is stored</AlertTitle>
        <AlertDescription>
          Your access token is held in memory only and discarded when the tab closes. The
          long-lived refresh token is kept in an HTTP-only cookie that page scripts cannot
          read.
        </AlertDescription>
      </Alert>

      <ConfirmDialog
        open={pendingRevoke !== null}
        onOpenChange={(open) => !open && setPendingRevoke(null)}
        title="Sign out this session?"
        description="That device will need to sign in again. Your current session is unaffected."
        confirmLabel="Sign out session"
        destructive
        onConfirm={async () => {
          if (!pendingRevoke) return;
          try {
            await revokeSession.mutateAsync(pendingRevoke.id);
            toast.success("Session signed out");
            setPendingRevoke(null);
          } catch (error) {
            toast.error("Couldn't sign out that session", {
              description: errorMessage(error),
            });
            throw error;
          }
        }}
      />
    </div>
  );
}
