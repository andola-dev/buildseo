"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Field, fieldAria } from "@/components/forms/field";
import { CLIENT_WEBSITE_STATUSES } from "@/config/enums";
import { CLIENT_WEBSITE_STATUS_LABELS } from "@/config/labels";
import { useCreateWebsite, useUpdateWebsite } from "@/features/websites/api/use-websites";
import { clientWebsiteSchema, normalizeUrl } from "@/lib/validation/schemas";
import { useFormErrors } from "@/lib/validation/use-form-errors";
import type { ClientWebsite, ClientWebsiteStatus } from "@/types/api";

interface WebsiteFormProps {
  /** Present when editing; absent when creating. */
  website?: ClientWebsite;
  onDone?: (website: ClientWebsite) => void;
  onCancel?: () => void;
}

/**
 * Create/edit form for a client website (spec §19).
 *
 * Fields mirror `ClientWebsiteCreate` / `ClientWebsiteUpdate`. The URL is
 * normalised to include a scheme before submission; the backend derives the
 * canonical domain itself, so nothing here tries to.
 */
export function WebsiteForm({ website, onDone, onCancel }: WebsiteFormProps) {
  const router = useRouter();
  const editing = Boolean(website);

  const [name, setName] = useState(website?.name ?? "");
  const [websiteUrl, setWebsiteUrl] = useState(website?.website_url ?? "");
  const [description, setDescription] = useState(website?.description ?? "");
  const [industry, setIndustry] = useState(website?.industry ?? "");
  const [country, setCountry] = useState(website?.target_country ?? "");
  const [language, setLanguage] = useState(website?.target_language ?? "");
  const [status, setStatus] = useState<ClientWebsiteStatus>(
    (website?.status as ClientWebsiteStatus | undefined) ?? "ACTIVE",
  );

  const { fieldError, formError, validate, applyServerError } = useFormErrors();
  const createWebsite = useCreateWebsite();
  const updateWebsite = useUpdateWebsite(website?.id ?? "");

  const submitting = createWebsite.isPending || updateWebsite.isPending;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    const values = validate(clientWebsiteSchema, {
      name,
      website_url: websiteUrl,
      description,
      industry,
      target_country: country,
      target_language: language,
    });
    if (!values) return;

    const payload = {
      name: values.name,
      website_url: normalizeUrl(values.website_url),
      description: values.description || null,
      industry: values.industry || null,
      target_country: values.target_country ? values.target_country.toUpperCase() : null,
      target_language: values.target_language || null,
    };

    try {
      const saved = editing
        ? await updateWebsite.mutateAsync({ ...payload, status })
        : await createWebsite.mutateAsync(payload);

      toast.success(editing ? "Website updated" : "Website added");

      if (onDone) onDone(saved);
      else router.push(`/websites/${saved.id}`);
    } catch (error) {
      applyServerError(error);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-6">
      {formError ? (
        <Alert variant="destructive">
          <AlertDescription>{formError}</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardContent className="grid gap-5 sm:grid-cols-2">
          <Field
            id="website-name"
            label="Website name"
            required
            error={fieldError("name")}
            className="sm:col-span-2"
          >
            <Input
              {...fieldAria("website-name", { error: fieldError("name") })}
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Acme SaaS"
            />
          </Field>

          <Field
            id="website-url"
            label="Website URL"
            required
            error={fieldError("website_url")}
            hint="The site you're building links to."
            className="sm:col-span-2"
          >
            <Input
              {...fieldAria("website-url", {
                error: fieldError("website_url"),
                hint: "The site you're building links to.",
              })}
              value={websiteUrl}
              onChange={(event) => setWebsiteUrl(event.target.value)}
              placeholder="acme.com"
              disabled={editing}
            />
          </Field>

          <Field id="website-industry" label="Industry" error={fieldError("industry")}>
            <Input
              {...fieldAria("website-industry", { error: fieldError("industry") })}
              value={industry}
              onChange={(event) => setIndustry(event.target.value)}
              placeholder="B2B software"
            />
          </Field>

          <Field
            id="website-country"
            label="Target country"
            error={fieldError("target_country")}
            hint="Two-letter code, e.g. US."
          >
            <Input
              {...fieldAria("website-country", {
                error: fieldError("target_country"),
                hint: "Two-letter code, e.g. US.",
              })}
              value={country}
              onChange={(event) => setCountry(event.target.value.toUpperCase())}
              placeholder="US"
              maxLength={2}
            />
          </Field>

          <Field
            id="website-language"
            label="Target language"
            error={fieldError("target_language")}
          >
            <Input
              {...fieldAria("website-language", { error: fieldError("target_language") })}
              value={language}
              onChange={(event) => setLanguage(event.target.value)}
              placeholder="en"
              maxLength={10}
            />
          </Field>

          {editing ? (
            <Field id="website-status" label="Status">
              <Select
                value={status}
                onValueChange={(value) => setStatus(value as ClientWebsiteStatus)}
              >
                <SelectTrigger id="website-status" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CLIENT_WEBSITE_STATUSES.map((option) => (
                    <SelectItem key={option} value={option}>
                      {CLIENT_WEBSITE_STATUS_LABELS[option]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
          ) : null}

          <Field
            id="website-description"
            label="Description"
            error={fieldError("description")}
            hint="Used as context when generating listing content."
            className="sm:col-span-2"
          >
            <Textarea
              {...fieldAria("website-description", {
                error: fieldError("description"),
                hint: "Used as context when generating listing content.",
              })}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              rows={4}
              placeholder="What the business does, who it serves, and what makes it distinctive."
            />
          </Field>
        </CardContent>
      </Card>

      <div className="flex items-center justify-end gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={onCancel ?? (() => router.back())}
          disabled={submitting}
        >
          Cancel
        </Button>
        <Button type="submit" loading={submitting}>
          {editing ? "Save changes" : "Add website"}
        </Button>
      </div>
    </form>
  );
}
