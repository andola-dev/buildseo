"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Check, ExternalLink, Send, X } from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DetailSkeleton } from "@/components/feedback/loading-state";
import { ErrorState } from "@/components/feedback/error-state";
import { DefinitionList } from "@/components/shared/definition-list";
import { FreeListingsBadge } from "@/components/shared/free-listings-badge";
import { PageHeader } from "@/components/shared/page-header";
import { PermissionGate } from "@/components/shared/permission-gate";
import { ScoreBar } from "@/components/shared/score-badge";
import { StatusBadge } from "@/components/shared/status-badge";
import {
  labelFor,
  OPPORTUNITY_STATUS_LABELS,
  OPPORTUNITY_TYPE_LABELS,
  PUBLISHER_STATUS_LABELS,
  SUBMISSION_METHOD_LABELS,
} from "@/config/labels";
import { PERM } from "@/config/permissions";
import { useCampaign } from "@/features/campaigns/api/use-campaigns";
import {
  useOpportunity,
  useSelectOpportunity,
} from "@/features/opportunities/api/use-opportunities";
import { AiContentPanel } from "@/features/opportunities/components/ai-content-panel";
import { RejectDialog } from "@/features/opportunities/components/reject-dialog";
import { usePublisher } from "@/features/publishers/api/use-publishers";
import { opportunitiesApi, submissionsApi } from "@/lib/api";
import { errorMessage } from "@/lib/api/errors";
import { useTenantId } from "@/lib/tenant/use-tenant";
import { queryKeys } from "@/lib/query/keys";
import { useQueryClient } from "@tanstack/react-query";
import { displayDomain, formatDateTime } from "@/lib/utils/format";

/** Opportunity detail with scores, recommendation and content prep (spec §26). */
export function OpportunityDetail({ opportunityId }: { opportunityId: string }) {
  const router = useRouter();
  const tenantId = useTenantId();
  const queryClient = useQueryClient();

  const opportunity = useOpportunity(opportunityId);
  const publisher = usePublisher(opportunity.data?.publisher_id);
  const campaign = useCampaign(opportunity.data?.campaign_id);
  const select = useSelectOpportunity(opportunityId);

  const [rejecting, setRejecting] = useState(false);
  const [busy, setBusy] = useState(false);

  if (opportunity.isPending) return <DetailSkeleton />;

  if (opportunity.error || !opportunity.data) {
    return (
      <ErrorState
        error={opportunity.error}
        resource="this opportunity"
        onRetry={() => void opportunity.refetch()}
      />
    );
  }

  const record = opportunity.data;

  const canApprove = ["DISCOVERED", "QUALIFIED"].includes(record.status);
  const canReject = !["REJECTED", "PUBLISHED", "SUBMITTED"].includes(record.status);
  const canPrepare = ["SELECTED", "READY"].includes(record.status);

  async function handleApprove() {
    setBusy(true);
    try {
      await select.mutateAsync();
      toast.success("Opportunity approved");
    } catch (error) {
      toast.error("Couldn't approve opportunity", { description: errorMessage(error) });
    } finally {
      setBusy(false);
    }
  }

  async function handlePrepare() {
    if (!tenantId) return;
    setBusy(true);
    try {
      const submission = await submissionsApi.createSubmission(tenantId, {
        opportunity_id: record.id,
        use_approved_content: true,
      });
      await queryClient.invalidateQueries({
        queryKey: queryKeys.opportunities.all(tenantId),
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.submissions.all(tenantId) });
      toast.success("Submission prepared");
      router.push(`/submissions/${submission.id}`);
    } catch (error) {
      toast.error("Couldn't prepare submission", { description: errorMessage(error) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title={record.suggested_title ?? "Listing opportunity"}
        description={
          publisher.data
            ? `${publisher.data.name ?? displayDomain(publisher.data.domain)} · ${displayDomain(publisher.data.domain)}`
            : undefined
        }
        badges={
          <>
            <StatusBadge status={record.status} labels={OPPORTUNITY_STATUS_LABELS} />
            <Badge variant="outline">
              {labelFor(OPPORTUNITY_TYPE_LABELS, record.opportunity_type)}
            </Badge>
            <FreeListingsBadge />
          </>
        }
        actions={
          <>
            {canApprove ? (
              <PermissionGate permission={PERM.OPPORTUNITY_UPDATE}>
                <Button size="sm" loading={busy} onClick={() => void handleApprove()}>
                  <Check className="size-4" aria-hidden />
                  Approve
                </Button>
              </PermissionGate>
            ) : null}

            {canPrepare ? (
              <PermissionGate permission={PERM.SUBMISSION_CREATE}>
                <Button size="sm" loading={busy} onClick={() => void handlePrepare()}>
                  <Send className="size-4" aria-hidden />
                  Prepare submission
                </Button>
              </PermissionGate>
            ) : null}

            {canReject ? (
              <PermissionGate permission={PERM.OPPORTUNITY_UPDATE}>
                <Button variant="outline" size="sm" onClick={() => setRejecting(true)}>
                  <X className="size-4" aria-hidden />
                  Reject
                </Button>
              </PermissionGate>
            ) : null}
          </>
        }
      />

      {record.status === "REJECTED" && record.rejection_reason ? (
        <Alert variant="destructive" className="mb-4">
          <X aria-hidden />
          <AlertTitle>Rejected</AlertTitle>
          <AlertDescription>{record.rejection_reason}</AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <AiContentPanel
            opportunityId={record.id}
            fallbackTitle={record.suggested_title}
            fallbackDescription={record.suggested_description}
            fallbackAnchor={record.suggested_anchor}
            fallbackCategory={record.category}
          />

          <Card>
            <CardHeader>
              <CardTitle>Publisher</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 pt-0">
              {publisher.isPending ? (
                <p className="text-muted-foreground text-sm">Loading publisher…</p>
              ) : publisher.data ? (
                <>
                  <DefinitionList
                    items={[
                      {
                        label: "Publisher",
                        value: (
                          <Link
                            href={`/publishers/${publisher.data.id}`}
                            className="hover:underline"
                          >
                            {publisher.data.name ?? displayDomain(publisher.data.domain)}
                          </Link>
                        ),
                      },
                      { label: "Domain", value: publisher.data.normalized_domain },
                      { label: "Country", value: publisher.data.country?.toUpperCase() },
                      { label: "Language", value: publisher.data.language },
                      {
                        label: "Publisher status",
                        value: (
                          <StatusBadge
                            status={publisher.data.status}
                            labels={PUBLISHER_STATUS_LABELS}
                          />
                        ),
                      },
                      {
                        label: "Submission method",
                        value: labelFor(
                          SUBMISSION_METHOD_LABELS,
                          publisher.data.submission_method,
                        ),
                      },
                      {
                        label: "Dofollow",
                        value:
                          publisher.data.dofollow_supported === null ||
                          publisher.data.dofollow_supported === undefined
                            ? "Unknown"
                            : publisher.data.dofollow_supported
                              ? "Supported"
                              : "Not supported",
                      },
                    ]}
                  />

                  {record.submission_url ?? publisher.data.submission_url ? (
                    <Button asChild variant="outline" size="sm">
                      <a
                        href={record.submission_url ?? publisher.data.submission_url ?? "#"}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        <ExternalLink className="size-4" aria-hidden />
                        Open submission page
                      </a>
                    </Button>
                  ) : null}
                </>
              ) : (
                <ErrorState error={publisher.error} resource="the publisher" />
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Scores</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 pt-0">
              <ScoreBar
                label="Opportunity score"
                score={record.qualification_score}
                kind="opportunity"
              />
              <ScoreBar
                label="Quality"
                score={publisher.data?.quality_score ?? null}
                kind="quality"
              />
              <ScoreBar
                label="Relevance"
                score={publisher.data?.relevance_score ?? null}
                kind="relevance"
              />
              <ScoreBar
                label="Authority"
                score={publisher.data?.authority_score ?? null}
                kind="authority"
              />
              <ScoreBar
                label="Spam risk"
                score={publisher.data?.spam_score ?? null}
                kind="spam"
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Opportunity</CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              <DefinitionList
                items={[
                  {
                    label: "Campaign",
                    value: campaign.data ? (
                      <Link
                        href={`/campaigns/${campaign.data.id}`}
                        className="hover:underline"
                      >
                        {campaign.data.name}
                      </Link>
                    ) : null,
                  },
                  {
                    label: "Type",
                    value: labelFor(OPPORTUNITY_TYPE_LABELS, record.opportunity_type),
                  },
                  { label: "Category", value: record.category },
                  { label: "Priority", value: record.priority },
                  {
                    label: "Target URL",
                    value: (
                      <a
                        href={record.target_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="hover:underline"
                      >
                        {displayDomain(record.target_url)}
                      </a>
                    ),
                  },
                  { label: "Anchor", value: record.suggested_anchor },
                  {
                    label: "Discovered",
                    value: record.discovered_at ? formatDateTime(record.discovered_at) : null,
                  },
                  {
                    label: "Qualified",
                    value: record.qualified_at ? formatDateTime(record.qualified_at) : null,
                  },
                ]}
              />
            </CardContent>
          </Card>
        </div>
      </div>

      <RejectDialog
        open={rejecting}
        onOpenChange={setRejecting}
        title="Reject this opportunity?"
        description="It won't be submitted. The reason is recorded for whoever reviews this campaign next."
        submitting={busy}
        onConfirm={async (reason) => {
          if (!tenantId) return;
          setBusy(true);
          try {
            await opportunitiesApi.rejectOpportunity(tenantId, record.id, { reason });
            await queryClient.invalidateQueries({
              queryKey: queryKeys.opportunities.all(tenantId),
            });
            toast.success("Opportunity rejected");
            setRejecting(false);
          } catch (error) {
            toast.error("Couldn't reject opportunity", { description: errorMessage(error) });
          } finally {
            setBusy(false);
          }
        }}
      />
    </>
  );
}
