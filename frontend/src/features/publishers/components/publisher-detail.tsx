"use client";

import { useState } from "react";
import Link from "next/link";
import { ExternalLink, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DetailSkeleton } from "@/components/feedback/loading-state";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { DefinitionList } from "@/components/shared/definition-list";
import { PageHeader } from "@/components/shared/page-header";
import { PermissionGate } from "@/components/shared/permission-gate";
import { ScoreBar } from "@/components/shared/score-badge";
import { StatusBadge } from "@/components/shared/status-badge";
import {
  labelFor,
  LINK_TYPE_LABELS,
  OPPORTUNITY_STATUS_LABELS,
  PRICING_TYPE_LABELS,
  PUBLISHER_CATEGORY_LABELS,
  PUBLISHER_STATUS_LABELS,
  SUBMISSION_METHOD_LABELS,
} from "@/config/labels";
import { PERM } from "@/config/permissions";
import {
  usePublisher,
  useQualifyPublisher,
} from "@/features/publishers/api/use-publishers";
import { useOpportunities } from "@/features/opportunities/api/use-opportunities";
import { errorMessage } from "@/lib/api/errors";
import {
  displayDomain,
  formatCompactNumber,
  formatDateTime,
  formatPercent,
} from "@/lib/utils/format";

/** Publisher detail: overview, metrics, submission info and history (spec §23). */
export function PublisherDetail({ publisherId }: { publisherId: string }) {
  const publisher = usePublisher(publisherId);
  const qualify = useQualifyPublisher(publisherId);
  const [requalifying, setRequalifying] = useState(false);

  /**
   * Campaign activity for this publisher.
   *
   * The backend has no `/publishers/{id}/history` endpoint, so the history
   * section is built from the opportunities that reference it — recorded under
   * "Known gaps" in docs/API_CONTRACT.md.
   */
  const activity = useOpportunities({
    page: 1,
    page_size: 25,
    publisher_id: publisherId,
    sort: "created_at",
    order: "desc",
  });

  if (publisher.isPending) return <DetailSkeleton />;

  if (publisher.error || !publisher.data) {
    return (
      <ErrorState
        error={publisher.error}
        resource="this publisher"
        onRetry={() => void publisher.refetch()}
      />
    );
  }

  const record = publisher.data;

  async function handleRequalify() {
    setRequalifying(true);
    try {
      const result = await qualify.mutateAsync({ fetch_live: true });
      toast.success("Publisher re-qualified", {
        description: `Recommended status: ${result.scores.recommended_status}`,
      });
    } catch (error) {
      toast.error("Couldn't qualify publisher", { description: errorMessage(error) });
    } finally {
      setRequalifying(false);
    }
  }

  return (
    <>
      <PageHeader
        title={record.name ?? displayDomain(record.domain)}
        description={displayDomain(record.domain)}
        badges={
          <>
            <StatusBadge status={record.status} labels={PUBLISHER_STATUS_LABELS} />
            <Badge variant={record.pricing_type === "FREE" ? "success" : "muted"}>
              {labelFor(PRICING_TYPE_LABELS, record.pricing_type)}
            </Badge>
            {record.is_submittable ? (
              <Badge variant="info">Submittable</Badge>
            ) : (
              <Badge variant="muted">Not submittable</Badge>
            )}
          </>
        }
        actions={
          <>
            <Button asChild variant="outline" size="sm">
              <a href={record.website_url} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="size-4" aria-hidden />
                Open site
              </a>
            </Button>
            <PermissionGate permission={PERM.PUBLISHER_QUALIFY}>
              <Button size="sm" loading={requalifying} onClick={() => void handleRequalify()}>
                <RefreshCw className="size-4" aria-hidden />
                Re-qualify
              </Button>
            </PermissionGate>
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Overview</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <DefinitionList
              items={[
                { label: "Publisher", value: record.name },
                { label: "Domain", value: record.normalized_domain },
                {
                  label: "Category",
                  value: labelFor(PUBLISHER_CATEGORY_LABELS, record.category),
                },
                { label: "Country", value: record.country?.toUpperCase() },
                { label: "Language", value: record.language },
                { label: "Link type", value: labelFor(LINK_TYPE_LABELS, record.link_type) },
              ]}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Scores</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 pt-0">
            <ScoreBar label="Quality" score={record.quality_score} kind="quality" />
            <ScoreBar label="Relevance" score={record.relevance_score} kind="relevance" />
            <ScoreBar label="Authority" score={record.authority_score} kind="authority" />
            <ScoreBar label="Spam risk" score={record.spam_score} kind="spam" />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Metrics</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <DefinitionList
              items={[
                {
                  label: "Organic traffic",
                  value: formatCompactNumber(record.organic_traffic),
                },
                {
                  label: "Authority",
                  value:
                    record.authority_score === null || record.authority_score === undefined
                      ? null
                      : Math.round(record.authority_score),
                },
                {
                  label: "Dofollow",
                  value:
                    record.dofollow_supported === null ||
                    record.dofollow_supported === undefined
                      ? "Unknown"
                      : record.dofollow_supported
                        ? "Supported"
                        : "Not supported",
                },
                {
                  label: "Nofollow",
                  value:
                    record.nofollow_supported === null ||
                    record.nofollow_supported === undefined
                      ? "Unknown"
                      : record.nofollow_supported
                        ? "Supported"
                        : "Not supported",
                },
                {
                  label: "Last checked",
                  value: record.last_checked_at
                    ? formatDateTime(record.last_checked_at)
                    : "Never",
                },
              ]}
            />
          </CardContent>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle>Submission</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 pt-0">
            <DefinitionList
              items={[
                {
                  label: "Method",
                  value: labelFor(SUBMISSION_METHOD_LABELS, record.submission_method),
                },
                {
                  label: "Pricing",
                  value: labelFor(PRICING_TYPE_LABELS, record.pricing_type),
                },
                {
                  label: "Submission page",
                  value: record.submission_url ? "Available" : "Not found",
                },
                { label: "Contact page", value: record.contact_url ? "Available" : "—" },
              ]}
            />

            {record.submission_url ? (
              <Button asChild variant="outline" size="sm" className="w-full">
                <a href={record.submission_url} target="_blank" rel="noopener noreferrer">
                  <ExternalLink className="size-4" aria-hidden />
                  Open submission page
                </a>
              </Button>
            ) : null}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Description &amp; signals</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 pt-0">
            {record.description ? (
              <p className="text-sm leading-relaxed">{record.description}</p>
            ) : (
              <p className="text-muted-foreground text-sm">
                No description captured for this publisher.
              </p>
            )}

            {record.signals && Object.keys(record.signals).length > 0 ? (
              <div>
                <h3 className="mb-2 text-xs font-medium tracking-wide uppercase">
                  Qualification signals
                </h3>
                <DefinitionList
                  items={Object.entries(record.signals).map(([key, value]) => ({
                    label: key.replace(/_/g, " "),
                    value:
                      typeof value === "boolean"
                        ? value
                          ? "Yes"
                          : "No"
                        : typeof value === "number"
                          ? key.includes("ratio") || key.includes("percent")
                            ? formatPercent(value * 100, 1)
                            : String(value)
                          : String(value),
                  }))}
                />
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle>Campaign activity</CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          {activity.isPending ? (
            <p className="text-muted-foreground text-sm">Loading activity…</p>
          ) : activity.error ? (
            <ErrorState
              error={activity.error}
              resource="this publisher's activity"
              onRetry={() => void activity.refetch()}
            />
          ) : (activity.data?.items.length ?? 0) === 0 ? (
            <EmptyState
              title="No campaign activity"
              description="This publisher hasn't been paired with a campaign yet. Opportunities appear here once it has."
            />
          ) : (
            <ul className="divide-y">
              {activity.data?.items.map((opportunity) => (
                <li key={opportunity.id} className="flex items-center gap-3 py-2.5">
                  <Link
                    href={`/opportunities/${opportunity.id}`}
                    className="min-w-0 flex-1 truncate text-sm hover:underline"
                  >
                    {opportunity.suggested_title ?? opportunity.target_url}
                  </Link>
                  <Link
                    href={`/campaigns/${opportunity.campaign_id}`}
                    className="text-muted-foreground shrink-0 text-xs hover:underline"
                  >
                    Campaign
                  </Link>
                  <StatusBadge
                    status={opportunity.status}
                    labels={OPPORTUNITY_STATUS_LABELS}
                  />
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </>
  );
}
