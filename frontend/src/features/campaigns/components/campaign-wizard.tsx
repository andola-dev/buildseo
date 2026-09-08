"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, ArrowRight, Check, Globe } from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { EmptyState } from "@/components/feedback/empty-state";
import { Field, fieldAria } from "@/components/forms/field";
import { DefinitionList } from "@/components/shared/definition-list";
import { FreeListingsBadge } from "@/components/shared/free-listings-badge";
import { useCreateCampaign } from "@/features/campaigns/api/use-campaigns";
import { useWebsiteOptions } from "@/features/websites/api/use-websites";
import { errorMessage, fieldErrorMap } from "@/lib/api/errors";
import { campaignSchema } from "@/lib/validation/schemas";
import { useFormErrors } from "@/lib/validation/use-form-errors";
import { displayDomain } from "@/lib/utils/format";
import { cn } from "@/lib/utils/cn";

/**
 * The six steps from spec §21.
 *
 * "Create campaign" is the submit action rather than a screen of its own, so
 * the wizard shows five panes and the sixth step is the button on Review.
 */
const STEPS = [
  { id: 1, title: "Client website", description: "Which site are you building links to?" },
  { id: 2, title: "Campaign details", description: "Name and describe the campaign." },
  { id: 3, title: "Target market", description: "Where should listings be found?" },
  { id: 4, title: "Link requirements", description: "How many links, and by when?" },
  { id: 5, title: "Review", description: "Check everything before creating." },
] as const;

/**
 * Which step renders each field.
 *
 * A backend validation error must be shown next to its field, and on the
 * Review step none of the fields are on screen — so the wizard navigates back
 * to the owning step rather than setting an error nobody can see.
 */
const FIELD_STEPS: Record<string, number> = {
  client_website_id: 1,
  name: 2,
  description: 2,
  target_country: 3,
  target_language: 3,
  target_link_count: 4,
  start_date: 4,
  end_date: 4,
};

function firstStepWithError(fields: readonly string[]): number | null {
  const steps = fields
    .map((field) => FIELD_STEPS[field])
    .filter((step): step is number => step !== undefined);

  return steps.length > 0 ? Math.min(...steps) : null;
}

interface WizardState {
  client_website_id: string;
  name: string;
  description: string;
  target_country: string;
  target_language: string;
  target_link_count: string;
  start_date: string;
  end_date: string;
}

function StepIndicator({ current }: { current: number }) {
  return (
    <ol className="mb-8 flex flex-wrap items-center gap-x-2 gap-y-2">
      {STEPS.map((step, index) => {
        const done = step.id < current;
        const active = step.id === current;

        return (
          <li key={step.id} className="flex items-center gap-2">
            <span
              aria-current={active ? "step" : undefined}
              className={cn(
                "flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-medium",
                done && "bg-primary text-primary-foreground",
                active && "border-primary text-primary border-2",
                !done && !active && "bg-muted text-muted-foreground",
              )}
            >
              {done ? <Check className="size-3.5" aria-hidden /> : step.id}
            </span>
            <span
              className={cn(
                "text-sm whitespace-nowrap",
                active ? "font-medium" : "text-muted-foreground",
              )}
            >
              {step.title}
            </span>
            {index < STEPS.length - 1 ? (
              <span className="bg-border mx-1 hidden h-px w-6 sm:block" aria-hidden />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

/**
 * Guided campaign creation (spec §21).
 *
 * State is held locally and submitted once at the end — the backend has no
 * draft-campaign endpoint, so creating a record per step would leave orphans
 * behind whenever a user abandoned the wizard.
 */
export function CampaignWizard() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const websites = useWebsiteOptions();
  const createCampaign = useCreateCampaign();
  const { fieldError, formError, setFormError, validate, applyServerError } = useFormErrors();

  const [step, setStep] = useState(1);
  const [values, setValues] = useState<WizardState>({
    // Pre-selects the website when arriving from a website detail page.
    client_website_id: searchParams.get("website") ?? "",
    name: "",
    description: "",
    target_country: "",
    target_language: "",
    target_link_count: "",
    start_date: "",
    end_date: "",
  });

  function set<K extends keyof WizardState>(key: K, value: WizardState[K]) {
    setValues((current) => ({ ...current, [key]: value }));
    setFormError(null);
  }

  const selectedWebsite = websites.data?.items.find(
    (website) => website.id === values.client_website_id,
  );

  /** Per-step gating, so Next can't skip a required field. */
  function canAdvance(): boolean {
    if (step === 1) return values.client_website_id !== "";
    if (step === 2) return values.name.trim().length >= 2;
    return true;
  }

  function parsedValues() {
    return validate(campaignSchema, {
      client_website_id: values.client_website_id,
      name: values.name,
      description: values.description,
      target_country: values.target_country,
      target_language: values.target_language,
      target_link_count:
        values.target_link_count === ""
          ? null
          : Number.parseInt(values.target_link_count, 10),
      start_date: values.start_date,
      end_date: values.end_date,
    });
  }

  async function handleCreate() {
    const parsed = parsedValues();
    if (!parsed) {
      // A validation failure belongs to an earlier step; send the user back to
      // the first one that can show the message.
      setStep(2);
      return;
    }

    if (parsed.start_date && parsed.end_date && parsed.end_date < parsed.start_date) {
      setFormError("The end date can't be before the start date.");
      setStep(4);
      return;
    }

    try {
      const campaign = await createCampaign.mutateAsync({
        client_website_id: parsed.client_website_id,
        name: parsed.name,
        description: parsed.description || null,
        target_country: parsed.target_country
          ? parsed.target_country.toUpperCase()
          : null,
        target_language: parsed.target_language || null,
        target_link_count: parsed.target_link_count,
        start_date: parsed.start_date || null,
        end_date: parsed.end_date || null,
      });

      toast.success("Campaign created", {
        description: `${campaign.name} is ready. Discover publishers to build its opportunity list.`,
      });
      router.push(`/campaigns/${campaign.id}`);
    } catch (error) {
      applyServerError(error);
      toast.error("Couldn't create campaign", { description: errorMessage(error) });

      // Go to the step that owns the rejected field, so the message is on
      // screen. The map is read from the error rather than from the hook's
      // state, which has not re-rendered yet at this point.
      const target = firstStepWithError(Object.keys(fieldErrorMap(error)));
      if (target !== null) setStep(target);
    }
  }

  if (websites.isPending) {
    return <p className="text-muted-foreground text-sm">Loading client websites…</p>;
  }

  // A campaign requires a website, so say so rather than presenting a picker
  // with nothing in it.
  if ((websites.data?.items.length ?? 0) === 0) {
    return (
      <Card>
        <EmptyState
          icon={Globe}
          title="Add a client website first"
          description="A campaign builds links for one client website, so you'll need at least one before creating a campaign."
          action={
            <Button size="sm" onClick={() => router.push("/websites/new")}>
              Add client website
            </Button>
          }
        />
      </Card>
    );
  }

  const currentStep = STEPS[step - 1];

  return (
    <div>
      <StepIndicator current={step} />

      {formError ? (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{formError}</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{currentStep?.title}</CardTitle>
          <p className="text-muted-foreground text-sm">{currentStep?.description}</p>
        </CardHeader>

        <CardContent className="space-y-5 pt-0">
          {step === 1 ? (
            <RadioGroup
              value={values.client_website_id}
              onValueChange={(value) => set("client_website_id", value)}
              className="gap-2"
            >
              {websites.data?.items.map((website) => (
                <Label
                  key={website.id}
                  htmlFor={`website-${website.id}`}
                  className={cn(
                    "hover:bg-accent/40 flex cursor-pointer items-start gap-3 rounded-lg border p-3 font-normal transition-colors",
                    values.client_website_id === website.id && "border-primary bg-accent/30",
                  )}
                >
                  <RadioGroupItem
                    id={`website-${website.id}`}
                    value={website.id}
                    className="mt-0.5"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{website.name}</span>
                    <span className="text-muted-foreground block truncate text-xs">
                      {displayDomain(website.website_url)}
                      {website.industry ? ` · ${website.industry}` : ""}
                    </span>
                  </span>
                </Label>
              ))}
            </RadioGroup>
          ) : null}

          {step === 2 ? (
            <>
              <Field
                id="campaign-name"
                label="Campaign name"
                required
                error={fieldError("name")}
              >
                <Input
                  {...fieldAria("campaign-name", { error: fieldError("name") })}
                  value={values.name}
                  onChange={(event) => set("name", event.target.value)}
                  placeholder="SaaS Directory Campaign"
                  autoFocus
                />
              </Field>

              <Field
                id="campaign-description"
                label="Description"
                error={fieldError("description")}
                hint="Optional. Helpful context for whoever reviews submissions."
              >
                <Textarea
                  {...fieldAria("campaign-description", {
                    error: fieldError("description"),
                    hint: "Optional. Helpful context for whoever reviews submissions.",
                  })}
                  value={values.description}
                  onChange={(event) => set("description", event.target.value)}
                  rows={4}
                />
              </Field>
            </>
          ) : null}

          {step === 3 ? (
            <div className="grid gap-5 sm:grid-cols-2">
              <Field
                id="campaign-country"
                label="Target country"
                error={fieldError("target_country")}
                hint="Two-letter code, e.g. US. Leave blank for global."
              >
                <Input
                  {...fieldAria("campaign-country", {
                    error: fieldError("target_country"),
                    hint: "Two-letter code, e.g. US. Leave blank for global.",
                  })}
                  value={values.target_country}
                  onChange={(event) => set("target_country", event.target.value.toUpperCase())}
                  placeholder="US"
                  maxLength={2}
                />
              </Field>

              <Field
                id="campaign-language"
                label="Target language"
                error={fieldError("target_language")}
                hint="Optional. e.g. en"
              >
                <Input
                  {...fieldAria("campaign-language", {
                    error: fieldError("target_language"),
                    hint: "Optional. e.g. en",
                  })}
                  value={values.target_language}
                  onChange={(event) => set("target_language", event.target.value)}
                  placeholder="en"
                  maxLength={10}
                />
              </Field>
            </div>
          ) : null}

          {step === 4 ? (
            <>
              {/* The MVP is free listings only, and the campaign says so
                  explicitly rather than offering a link-type choice
                  (spec §21/§73). */}
              <div className="bg-muted/40 flex items-center justify-between gap-3 rounded-lg border p-3">
                <div>
                  <div className="text-sm font-medium">Link type</div>
                  <p className="text-muted-foreground text-xs">
                    This workspace submits to free directories and listing sites only. Paid
                    placements aren&apos;t available.
                  </p>
                </div>
                <FreeListingsBadge />
              </div>

              <Field
                id="campaign-target-links"
                label="Target link count"
                error={fieldError("target_link_count")}
                hint="Optional. Used to show campaign progress."
              >
                <Input
                  {...fieldAria("campaign-target-links", {
                    error: fieldError("target_link_count"),
                    hint: "Optional. Used to show campaign progress.",
                  })}
                  type="number"
                  inputMode="numeric"
                  min={1}
                  value={values.target_link_count}
                  onChange={(event) => set("target_link_count", event.target.value)}
                  placeholder="250"
                />
              </Field>

              <div className="grid gap-5 sm:grid-cols-2">
                <Field id="campaign-start" label="Start date" error={fieldError("start_date")}>
                  <Input
                    {...fieldAria("campaign-start", { error: fieldError("start_date") })}
                    type="date"
                    value={values.start_date}
                    onChange={(event) => set("start_date", event.target.value)}
                  />
                </Field>

                <Field id="campaign-end" label="End date" error={fieldError("end_date")}>
                  <Input
                    {...fieldAria("campaign-end", { error: fieldError("end_date") })}
                    type="date"
                    value={values.end_date}
                    onChange={(event) => set("end_date", event.target.value)}
                  />
                </Field>
              </div>
            </>
          ) : null}

          {step === 5 ? (
            <>
              <DefinitionList
                items={[
                  { label: "Client website", value: selectedWebsite?.name },
                  {
                    label: "Domain",
                    value: selectedWebsite ? displayDomain(selectedWebsite.website_url) : null,
                  },
                  { label: "Campaign name", value: values.name },
                  { label: "Description", value: values.description || null },
                  { label: "Target country", value: values.target_country || "Global" },
                  { label: "Target language", value: values.target_language || "Any" },
                  {
                    label: "Target links",
                    value: values.target_link_count || "No target",
                  },
                  { label: "Start date", value: values.start_date || null },
                  { label: "End date", value: values.end_date || null },
                  { label: "Link type", value: <FreeListingsBadge /> },
                ]}
              />
              <Separator />
              <p className="text-muted-foreground text-sm">
                The campaign is created as a draft. Run discovery next to build its publisher
                and opportunity lists.
              </p>
            </>
          ) : null}
        </CardContent>
      </Card>

      <div className="mt-6 flex items-center justify-between gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={() => (step === 1 ? router.back() : setStep(step - 1))}
          disabled={createCampaign.isPending}
        >
          <ArrowLeft className="size-4" aria-hidden />
          {step === 1 ? "Cancel" : "Back"}
        </Button>

        {step < STEPS.length ? (
          <Button type="button" onClick={() => setStep(step + 1)} disabled={!canAdvance()}>
            Continue
            <ArrowRight className="size-4" aria-hidden />
          </Button>
        ) : (
          <Button
            type="button"
            onClick={() => void handleCreate()}
            loading={createCampaign.isPending}
          >
            Create campaign
          </Button>
        )}
      </div>
    </div>
  );
}
