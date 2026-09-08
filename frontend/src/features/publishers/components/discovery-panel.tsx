"use client";

import { useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AlertCircle, Loader2, Play, Search } from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { Field, fieldAria } from "@/components/forms/field";
import { FreeListingsBadge } from "@/components/shared/free-listings-badge";
import { StatusBadge } from "@/components/shared/status-badge";
import { IN_FLIGHT_STATUSES, PUBLISHER_CATEGORIES } from "@/config/enums";
import { PUBLISHER_CATEGORY_LABELS } from "@/config/labels";
import { useCampaignOptions } from "@/features/campaigns/api/use-campaigns";
import {
  useDiscoveryProviders,
  useDiscoveryRuns,
  useStartDiscovery,
} from "@/features/publishers/api/use-discovery";
import { errorMessage } from "@/lib/api/errors";
import { discoverySchema, parseKeywords } from "@/lib/validation/schemas";
import { useFormErrors } from "@/lib/validation/use-form-errors";
import { formatDateTime, formatNumber } from "@/lib/utils/format";
import type { DiscoveryRun } from "@/types/api";

/** Live counters for one run: discovered → created → skipped (spec §24). */
function RunProgress({ run }: { run: DiscoveryRun }) {
  const active = IN_FLIGHT_STATUSES.includes(run.status);

  const counters = [
    { label: "Found", value: run.results_found },
    { label: "Added", value: run.publishers_created },
    { label: "Duplicates skipped", value: run.duplicates_skipped },
  ];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={run.status} />
        <span className="text-muted-foreground text-xs">{run.provider}</span>
        {active ? (
          <span className="text-muted-foreground flex items-center gap-1 text-xs">
            <Loader2 className="size-3 animate-spin" aria-hidden />
            Working…
          </span>
        ) : null}
      </div>

      <dl className="grid grid-cols-3 gap-3">
        {counters.map((counter) => (
          <div key={counter.label} className="bg-muted/40 rounded-md px-3 py-2">
            <dt className="text-muted-foreground text-xs">{counter.label}</dt>
            <dd className="tabular text-lg font-semibold">{formatNumber(counter.value)}</dd>
          </div>
        ))}
      </dl>

      {run.error ? (
        <Alert variant="destructive">
          <AlertCircle aria-hidden />
          <AlertTitle>Discovery failed</AlertTitle>
          <AlertDescription>{run.error}</AlertDescription>
        </Alert>
      ) : null}

      <div className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-xs">
        <span>Started {run.started_at ? formatDateTime(run.started_at) : "—"}</span>
        <span>Finished {run.finished_at ? formatDateTime(run.finished_at) : "—"}</span>
      </div>

      {run.publishers_created > 0 ? (
        <Button asChild variant="outline" size="sm">
          <Link href="/publishers?status=DISCOVERED">Review discovered publishers</Link>
        </Button>
      ) : null}
    </div>
  );
}

/**
 * Publisher discovery (spec §24).
 *
 * Discovery is a backend job: submitting enqueues it and the run list polls
 * until it finishes, so the browser is never blocked on a crawl and results
 * appear progressively. Nothing here crawls anything itself.
 */
export function DiscoveryPanel() {
  const searchParams = useSearchParams();
  const providers = useDiscoveryProviders();
  const campaigns = useCampaignOptions();
  const startDiscovery = useStartDiscovery();
  const { fieldError, formError, validate, applyServerError } = useFormErrors();

  const [provider, setProvider] = useState("");
  const [keywords, setKeywords] = useState("");
  const [country, setCountry] = useState("");
  const [language, setLanguage] = useState("");
  const [category, setCategory] = useState("");
  const [campaignId, setCampaignId] = useState(searchParams.get("campaign") ?? "");
  const [limit, setLimit] = useState("25");

  const runs = useDiscoveryRuns({ page: 1, page_size: 10, sort: "created_at", order: "desc" });

  // Default to the first available provider once the list loads.
  const availableProviders = (providers.data ?? []).filter((entry) => entry.available);
  const effectiveProvider = provider || availableProviders[0]?.key || "";

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    const values = validate(discoverySchema, {
      provider: effectiveProvider,
      keywords,
      country,
      language,
      category,
      campaign_id: campaignId,
      limit: Number.parseInt(limit, 10) || 25,
    });
    if (!values) return;

    try {
      const result = await startDiscovery.mutateAsync({
        provider: values.provider,
        keywords: parseKeywords(values.keywords),
        country: values.country ? values.country.toUpperCase() : null,
        language: values.language || null,
        category: values.category
          ? (values.category as (typeof PUBLISHER_CATEGORIES)[number])
          : null,
        campaign_id: values.campaign_id || null,
        limit: values.limit,
      });

      if (result.kind === "job") {
        toast.success("Discovery started", {
          description: "Results appear below as publishers are found.",
        });
      } else {
        toast.success("Discovery finished", {
          description: `${result.run.publishers_created} publisher(s) added.`,
        });
      }

      await runs.refetch();
    } catch (error) {
      applyServerError(error);
      toast.error("Couldn't start discovery", { description: errorMessage(error) });
    }
  }

  const noProviders = providers.data !== undefined && availableProviders.length === 0;

  return (
    <div className="grid gap-4 lg:grid-cols-5">
      <Card className="lg:col-span-2">
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <CardTitle>Discovery criteria</CardTitle>
            <FreeListingsBadge />
          </div>
        </CardHeader>

        <CardContent className="pt-0">
          {noProviders ? (
            <Alert variant="warning" className="mb-4">
              <AlertCircle aria-hidden />
              <AlertTitle>No discovery provider available</AlertTitle>
              <AlertDescription>
                Discovery providers need a credential configured for this workspace. Add one
                in{" "}
                <Link href="/settings/integrations" className="underline underline-offset-4">
                  Settings → Integrations
                </Link>
                .
              </AlertDescription>
            </Alert>
          ) : null}

          {formError ? (
            <Alert variant="destructive" className="mb-4">
              <AlertDescription>{formError}</AlertDescription>
            </Alert>
          ) : null}

          <form onSubmit={handleSubmit} noValidate className="space-y-4">
            <Field
              id="discovery-provider"
              label="Provider"
              required
              error={fieldError("provider")}
            >
              <Select
                value={effectiveProvider}
                onValueChange={setProvider}
                disabled={providers.isPending || availableProviders.length === 0}
              >
                <SelectTrigger id="discovery-provider" className="w-full">
                  <SelectValue placeholder="Choose a provider" />
                </SelectTrigger>
                <SelectContent>
                  {(providers.data ?? []).map((entry) => (
                    <SelectItem key={entry.key} value={entry.key} disabled={!entry.available}>
                      <span className="flex items-center gap-2">
                        {entry.name}
                        {entry.available ? null : (
                          <Badge variant="muted">Needs credential</Badge>
                        )}
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>

            <Field
              id="discovery-keywords"
              label="Keywords"
              required
              error={fieldError("keywords")}
              hint="One per line, or comma separated. e.g. saas directory, startup listing"
            >
              <Textarea
                {...fieldAria("discovery-keywords", {
                  error: fieldError("keywords"),
                  hint: "One per line, or comma separated. e.g. saas directory, startup listing",
                })}
                value={keywords}
                onChange={(event) => setKeywords(event.target.value)}
                rows={3}
                placeholder={"saas directory\nstartup listing"}
              />
            </Field>

            <Field id="discovery-category" label="Directory type" error={fieldError("category")}>
              <Select value={category} onValueChange={setCategory}>
                <SelectTrigger id="discovery-category" className="w-full">
                  <SelectValue placeholder="Any" />
                </SelectTrigger>
                <SelectContent>
                  {PUBLISHER_CATEGORIES.map((option) => (
                    <SelectItem key={option} value={option}>
                      {PUBLISHER_CATEGORY_LABELS[option]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field id="discovery-country" label="Country" error={fieldError("country")}>
                <Input
                  {...fieldAria("discovery-country", { error: fieldError("country") })}
                  value={country}
                  onChange={(event) => setCountry(event.target.value.toUpperCase())}
                  placeholder="US"
                  maxLength={2}
                />
              </Field>

              <Field id="discovery-language" label="Language" error={fieldError("language")}>
                <Input
                  {...fieldAria("discovery-language", { error: fieldError("language") })}
                  value={language}
                  onChange={(event) => setLanguage(event.target.value)}
                  placeholder="en"
                  maxLength={10}
                />
              </Field>
            </div>

            <Field
              id="discovery-campaign"
              label="Attach to campaign"
              error={fieldError("campaign_id")}
              hint="Optional. Links the discovered publishers to a campaign."
            >
              <Select value={campaignId} onValueChange={setCampaignId}>
                <SelectTrigger id="discovery-campaign" className="w-full">
                  <SelectValue placeholder="None" />
                </SelectTrigger>
                <SelectContent>
                  {(campaigns.data?.items ?? []).map((campaign) => (
                    <SelectItem key={campaign.id} value={campaign.id}>
                      {campaign.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>

            <Field id="discovery-limit" label="Result limit" error={fieldError("limit")}>
              <Input
                {...fieldAria("discovery-limit", { error: fieldError("limit") })}
                type="number"
                min={1}
                max={200}
                value={limit}
                onChange={(event) => setLimit(event.target.value)}
              />
            </Field>

            <Button
              type="submit"
              className="w-full"
              loading={startDiscovery.isPending}
              disabled={availableProviders.length === 0}
            >
              <Play className="size-4" aria-hidden />
              Start discovery
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card className="lg:col-span-3">
        <CardHeader>
          <CardTitle>Discovery runs</CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          {runs.isPending ? (
            <p className="text-muted-foreground text-sm">Loading runs…</p>
          ) : runs.error ? (
            <ErrorState
              error={runs.error}
              resource="discovery runs"
              onRetry={() => void runs.refetch()}
            />
          ) : (runs.data?.items.length ?? 0) === 0 ? (
            <EmptyState
              icon={Search}
              title="No discovery runs yet"
              description="Set your criteria and start discovery. Runs appear here with live counters as publishers are found."
            />
          ) : (
            <ul className="space-y-4 divide-y">
              {runs.data?.items.map((run) => (
                <li key={run.id} className="pt-4 first:pt-0">
                  <RunProgress run={run} />
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
