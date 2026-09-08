"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Field, fieldAria } from "@/components/forms/field";
import { DefinitionList } from "@/components/shared/definition-list";
import { meApi } from "@/lib/api";
import { useAuth } from "@/lib/auth/auth-provider";
import { profileSchema } from "@/lib/validation/schemas";
import { useFormErrors } from "@/lib/validation/use-form-errors";
import { formatDateTime, initials, userDisplayName } from "@/lib/utils/format";
import { useMutation } from "@tanstack/react-query";

/**
 * The user's own profile (spec §10).
 *
 * The backend accepts only the name fields on `PATCH /me`; the email address is
 * the login identity and is not editable here.
 */
export function ProfileSettings() {
  const { user, refetchSession } = useAuth();
  const { fieldError, formError, validate, applyServerError } = useFormErrors();

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");

  useEffect(() => {
    setFirstName(user?.first_name ?? "");
    setLastName(user?.last_name ?? "");
  }, [user]);

  const updateProfile = useMutation({
    mutationFn: meApi.updateMe,
    onSuccess: async () => {
      await refetchSession();
    },
  });

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    const values = validate(profileSchema, { first_name: firstName, last_name: lastName });
    if (!values) return;

    try {
      await updateProfile.mutateAsync({
        first_name: values.first_name || null,
        last_name: values.last_name || null,
      });
      toast.success("Profile updated");
    } catch (error) {
      applyServerError(error);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-semibold">Profile</h2>
        <p className="text-muted-foreground text-sm">
          Your name as it appears to the rest of your team.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Your details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5 pt-0">
          <div className="flex items-center gap-3">
            <Avatar className="size-11">
              <AvatarFallback>
                {initials(userDisplayName(user), user?.email)}
              </AvatarFallback>
            </Avatar>
            <div className="min-w-0">
              <div className="truncate text-sm font-medium">{userDisplayName(user)}</div>
              <div className="text-muted-foreground truncate text-xs">{user?.email}</div>
            </div>
          </div>

          <form onSubmit={handleSubmit} noValidate className="space-y-4">
            {formError ? (
              <Alert variant="destructive">
                <AlertDescription>{formError}</AlertDescription>
              </Alert>
            ) : null}

            <div className="grid gap-4 sm:grid-cols-2">
              <Field id="first-name" label="First name" error={fieldError("first_name")}>
                <Input
                  {...fieldAria("first-name", { error: fieldError("first_name") })}
                  value={firstName}
                  onChange={(event) => setFirstName(event.target.value)}
                />
              </Field>

              <Field id="last-name" label="Last name" error={fieldError("last_name")}>
                <Input
                  {...fieldAria("last-name", { error: fieldError("last_name") })}
                  value={lastName}
                  onChange={(event) => setLastName(event.target.value)}
                />
              </Field>
            </div>

            <Button type="submit" size="sm" loading={updateProfile.isPending}>
              Save profile
            </Button>
          </form>

          <DefinitionList
            items={[
              { label: "Email", value: user?.email },
              {
                label: "Email verified",
                value: user?.is_verified ? "Yes" : "No",
              },
              {
                label: "Last sign-in",
                value: user?.last_login_at ? formatDateTime(user.last_login_at) : "—",
              },
            ]}
          />
        </CardContent>
      </Card>
    </div>
  );
}
