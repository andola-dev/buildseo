"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Check, Loader2, RefreshCw, Sparkles, X } from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { Field } from "@/components/forms/field";
import { PermissionGate } from "@/components/shared/permission-gate";
import { StatusBadge } from "@/components/shared/status-badge";
import { CONTENT_STATUS_LABELS } from "@/config/labels";
import { PERM } from "@/config/permissions";
import {
  useGenerateContent,
  useGeneratedContent,
  useReviewContent,
} from "@/features/opportunities/api/use-opportunities";
import { errorMessage, isApiError } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/utils/format";
import type { GeneratedContent, GeneratedContentPayload } from "@/types/api";

/**
 * Read the generator's output.
 *
 * `generated_content` is an open object on the wire, so each field is checked
 * rather than assumed — a provider that omits one must not crash the panel.
 */
function readPayload(content: GeneratedContent): GeneratedContentPayload {
  const raw = content.generated_content;
  return typeof raw === "object" && raw !== null ? (raw as GeneratedContentPayload) : {};
}

interface DraftFields {
  title: string;
  description: string;
  category: string;
  anchor_text: string;
}

function toDraft(payload: GeneratedContentPayload): DraftFields {
  return {
    title: payload.title ?? "",
    description: payload.long_description ?? payload.description ?? payload.short_description ?? "",
    category: payload.category ?? "",
    anchor_text: payload.anchor_text ?? "",
  };
}

/**
 * AI-generated listing content (spec §27).
 *
 * Generation is a backend call that uses the workspace's stored BYOK
 * credential — no provider key is ever sent from or held by the browser
 * (spec §27/§48). The generated copy is editable, and what the reviewer
 * approves is what gets stored.
 */
export function AiContentPanel({
  opportunityId,
  fallbackTitle,
  fallbackDescription,
  fallbackAnchor,
  fallbackCategory,
}: {
  opportunityId: string;
  fallbackTitle?: string | null;
  fallbackDescription?: string | null;
  fallbackAnchor?: string | null;
  fallbackCategory?: string | null;
}) {
  const drafts = useGeneratedContent(opportunityId);
  const generate = useGenerateContent(opportunityId);
  const review = useReviewContent(opportunityId);

  // The newest draft is what the reviewer works on; older ones are history.
  const latest = drafts.data?.[0];
  const [draft, setDraft] = useState<DraftFields | null>(null);

  useEffect(() => {
    if (!latest) {
      setDraft(null);
      return;
    }
    setDraft(toDraft(readPayload(latest)));
  }, [latest]);

  async function handleGenerate(regenerate: boolean) {
    try {
      await generate.mutateAsync({
        regenerate,
        include_short_description: true,
        include_long_description: true,
      });
      toast.success(regenerate ? "Content regenerated" : "Content generated");
    } catch (error) {
      // A missing credential is the common case and deserves a pointer to the
      // page that fixes it rather than a bare error.
      if (isApiError(error) && error.code === "CREDENTIAL_NOT_CONFIGURED") {
        toast.error("No AI provider configured", {
          description: "Add a provider key in Settings → AI Providers.",
        });
        return;
      }
      toast.error("Couldn't generate content", { description: errorMessage(error) });
    }
  }

  async function handleAccept() {
    if (!latest || !draft) return;

    try {
      await review.mutateAsync({
        contentId: latest.id,
        payload: {
          decision: "APPROVED",
          // Send the reviewer's edits so the approved copy is what they saw.
          edited_content: {
            title: draft.title,
            description: draft.description,
            long_description: draft.description,
            category: draft.category,
            anchor_text: draft.anchor_text,
          },
        },
      });
      toast.success("Content approved", {
        description: "It will be used when a submission is prepared.",
      });
    } catch (error) {
      toast.error("Couldn't approve content", { description: errorMessage(error) });
    }
  }

  async function handleReject() {
    if (!latest) return;
    try {
      await review.mutateAsync({
        contentId: latest.id,
        payload: { decision: "REJECTED" },
      });
      toast.success("Draft rejected", { description: "Generate a new one when ready." });
    } catch (error) {
      toast.error("Couldn't reject content", { description: errorMessage(error) });
    }
  }

  const generating = generate.isPending;

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="text-muted-foreground size-4" aria-hidden />
            Listing content
          </CardTitle>

          <div className="flex items-center gap-2">
            {latest ? (
              <StatusBadge status={latest.content_status} labels={CONTENT_STATUS_LABELS} />
            ) : null}
            <PermissionGate permission={PERM.AI_GENERATE}>
              <Button
                variant={latest ? "outline" : "default"}
                size="sm"
                loading={generating}
                onClick={() => void handleGenerate(Boolean(latest))}
              >
                {latest ? (
                  <>
                    <RefreshCw className="size-4" aria-hidden />
                    Regenerate
                  </>
                ) : (
                  <>
                    <Sparkles className="size-4" aria-hidden />
                    Generate with AI
                  </>
                )}
              </Button>
            </PermissionGate>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4 pt-0">
        {generating ? (
          <div
            className="space-y-3"
            role="status"
            aria-live="polite"
            aria-label="Generating content"
          >
            <p className="text-muted-foreground flex items-center gap-2 text-sm">
              <Loader2 className="size-3.5 animate-spin" aria-hidden />
              Generating…
            </p>
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-9 w-1/2" />
          </div>
        ) : drafts.isPending ? (
          <div className="space-y-3" aria-hidden>
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : drafts.error ? (
          <ErrorState
            error={drafts.error}
            resource="generated content"
            onRetry={() => void drafts.refetch()}
          />
        ) : !latest || !draft ? (
          <>
            {/* Whatever the discovery/scoring step suggested, shown so the
                reviewer isn't looking at a blank panel before generating. */}
            {fallbackTitle || fallbackDescription ? (
              <div className="space-y-3 rounded-lg border p-3">
                <Badge variant="muted">Suggested during qualification</Badge>
                {fallbackTitle ? (
                  <div>
                    <div className="text-muted-foreground text-xs">Title</div>
                    <div className="text-sm">{fallbackTitle}</div>
                  </div>
                ) : null}
                {fallbackDescription ? (
                  <div>
                    <div className="text-muted-foreground text-xs">Description</div>
                    <p className="text-sm leading-relaxed">{fallbackDescription}</p>
                  </div>
                ) : null}
                {fallbackAnchor ? (
                  <div>
                    <div className="text-muted-foreground text-xs">Anchor</div>
                    <div className="text-sm">{fallbackAnchor}</div>
                  </div>
                ) : null}
                {fallbackCategory ? (
                  <div>
                    <div className="text-muted-foreground text-xs">Category</div>
                    <div className="text-sm">{fallbackCategory}</div>
                  </div>
                ) : null}
              </div>
            ) : (
              <EmptyState
                icon={Sparkles}
                title="No listing content yet"
                description="Generate a title, description, category and anchor for this listing, then review and edit before submitting."
              />
            )}

            <Alert variant="info">
              <Sparkles aria-hidden />
              <AlertTitle>Generation happens on the server</AlertTitle>
              <AlertDescription>
                Your provider key is stored encrypted and used by the backend. It is never
                sent to or held by your browser. Configure providers in{" "}
                <Link href="/settings/ai" className="underline underline-offset-4">
                  Settings → AI Providers
                </Link>
                .
              </AlertDescription>
            </Alert>
          </>
        ) : (
          <>
            <div className="text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
              {latest.ai_provider ? <span>Provider: {latest.ai_provider}</span> : null}
              {latest.ai_model ? <span>Model: {latest.ai_model}</span> : null}
              {latest.generation_timestamp ? (
                <span>Generated {formatDateTime(latest.generation_timestamp)}</span>
              ) : null}
            </div>

            <Field id="ai-title" label="Title">
              <Input
                id="ai-title"
                value={draft.title}
                onChange={(event) => setDraft({ ...draft, title: event.target.value })}
              />
            </Field>

            <Field id="ai-description" label="Description">
              <Textarea
                id="ai-description"
                value={draft.description}
                onChange={(event) => setDraft({ ...draft, description: event.target.value })}
                rows={6}
              />
            </Field>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field id="ai-category" label="Category">
                <Input
                  id="ai-category"
                  value={draft.category}
                  onChange={(event) => setDraft({ ...draft, category: event.target.value })}
                />
              </Field>

              <Field id="ai-anchor" label="Anchor text">
                <Input
                  id="ai-anchor"
                  value={draft.anchor_text}
                  onChange={(event) =>
                    setDraft({ ...draft, anchor_text: event.target.value })
                  }
                />
              </Field>
            </div>

            {latest.review_notes ? (
              <Alert>
                <AlertTitle>Review notes</AlertTitle>
                <AlertDescription>{latest.review_notes}</AlertDescription>
              </Alert>
            ) : null}

            {latest.content_status === "APPROVED" ? (
              <Alert variant="success">
                <Check aria-hidden />
                <AlertTitle>Approved</AlertTitle>
                <AlertDescription>
                  This copy will be used when a submission is prepared.
                </AlertDescription>
              </Alert>
            ) : (
              <PermissionGate permission={PERM.OPPORTUNITY_UPDATE}>
                <div className="flex items-center justify-end gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    loading={review.isPending}
                    onClick={() => void handleReject()}
                  >
                    <X className="size-4" aria-hidden />
                    Reject draft
                  </Button>
                  <Button
                    size="sm"
                    loading={review.isPending}
                    onClick={() => void handleAccept()}
                  >
                    <Check className="size-4" aria-hidden />
                    Accept
                  </Button>
                </div>
              </PermissionGate>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
