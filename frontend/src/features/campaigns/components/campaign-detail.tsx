"use client";

import { useState } from "react";
import Link from "next/link";
import { Link2, Search, Send, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { DetailSkeleton } from "@/components/feedback/loading-state";
import { ErrorState } from "@/components/feedback/error-state";
import { DefinitionList } from "@/components/shared/definition-list";
import { FreeListingsBadge } from "@/components/shared/free-listings-badge";
import { PageHeader } from "@/components/shared/page-header";
import { PermissionGate } from "@/components/shared/permission-gate";
import { ProgressCard } from "@/components/shared/progress-card";
import { StatusBadge } from "@/components/shared/status-badge";
import { CampaignFunnel } from "@/features/campaigns/components/campaign-funnel";
import { CAMPAIGN_STATUSES } from "@/config/enums";
import { CAMPAIGN_STATUS_LABELS } from "@/config/labels";
import { PERM } from "@/config/permissions";
import {
  useCampaign,
  useCampaignStats,
  useUpdateCampaign,
} from "@/features/campaigns/api/use-campaigns";
import { useWebsite } from "@/features/websites/api/use-websites";
import { errorMessage } from "@/lib/api/errors";
import { formatDate, formatNumber } from "@/lib/utils/format";
import type { CampaignStatus } from "@/types/api";

/** Campaign detail: funnel, progress and the next workflow step (spec §20). */
export function CampaignDetail({ campaignId }: { campaignId: string }) {
  const campaign = useCampaign(campaignId);
  const stats = useCampaignStats(campaignId);
  const website = useWebsite(campaign.data?.client_website_id);
  const updateCampaign = useUpdateCampaign(campaignId);
  const [statusPending, setStatusPending] = useState(false);

  if (campaign.isPending) return <DetailSkeleton />;

  if (campaign.error || !campaign.data) {
    return (
      <ErrorState
        error={campaign.error}
        resource="this campaign"
        onRetry={() => void campaign.refetch()}
      />
    );
  }

  const record = campaign.data;

  async function handleStatusChange(status: CampaignStatus) {
    setStatusPending(true);
    try {
      await updateCampaign.mutateAsync({ status });
      toast.success(`Campaign marked ${CAMPAIGN_STATUS_LABELS[status].toLowerCase()}`);
    } catch (error) {
      toast.error("Couldn't update campaign", { description: errorMessage(error) });
    } finally {
      setStatusPending(false);
    }
  }

  return (
    <>
      <PageHeader
        title={record.name}
        description={record.description ?? undefined}
        badges={
          <>
            <StatusBadge status={record.status} labels={CAMPAIGN_STATUS_LABELS} />
            {record.free_only ? <FreeListingsBadge /> : null}
          </>
        }
        actions={
          <>
            <PermissionGate permission={PERM.PUBLISHER_DISCOVER}>
              <Button asChild variant="outline" size="sm">
                <Link href={`/publishers/discovery?campaign=${record.id}`}>
                  <Search className="size-4" aria-hidden />
                  Discover publishers
                </Link>
              </Button>
            </PermissionGate>

            <PermissionGate permission={PERM.CAMPAIGN_UPDATE}>
              <Select
                value={record.status}
                onValueChange={(value) => void handleStatusChange(value as CampaignStatus)}
                disabled={statusPending}
              >
                <SelectTrigger size="sm" className="w-36" aria-label="Campaign status">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CAMPAIGN_STATUSES.map((status) => (
                    <SelectItem key={status} value={status}>
                      {CAMPAIGN_STATUS_LABELS[status]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </PermissionGate>
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Campaign performance</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            {stats.isPending ? (
              <p className="text-muted-foreground text-sm">Loading counters…</p>
            ) : stats.error ? (
              <ErrorState
                error={stats.error}
                resource="campaign statistics"
                onRetry={() => void stats.refetch()}
              />
            ) : stats.data ? (
              <>
                <CampaignFunnel stats={stats.data} campaignId={record.id} />
                <div className="mt-6 border-t pt-4">
                  <ProgressCard
                    title="Published links"
                    subtitle={record.name}
                    current={stats.data.submissions_published}
                    target={stats.data.target_link_count ?? record.target_link_count}
                  />
                </div>
              </>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Details</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <DefinitionList
              items={[
                {
                  label: "Client website",
                  value: website.data ? (
                    <Link
                      href={`/websites/${website.data.id}`}
                      className="hover:underline"
                    >
                      {website.data.name}
                    </Link>
                  ) : null,
                },
                {
                  label: "Target links",
                  value: record.target_link_count
                    ? formatNumber(record.target_link_count)
                    : "No target",
                },
                { label: "Target country", value: record.target_country?.toUpperCase() },
                { label: "Target language", value: record.target_language },
                { label: "Start date", value: record.start_date ? formatDate(record.start_date) : null },
                { label: "End date", value: record.end_date ? formatDate(record.end_date) : null },
                { label: "Created", value: formatDate(record.created_at) },
              ]}
            />
          </CardContent>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Card>
          <CardContent className="flex items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 text-sm font-medium">
                <Link2 className="text-muted-foreground size-4" aria-hidden />
                Opportunities
              </div>
              <p className="text-muted-foreground mt-1 text-xs">
                Review and approve free listing opportunities for this campaign.
              </p>
            </div>
            <Button asChild variant="outline" size="sm">
              <Link href={`/opportunities?campaign_id=${record.id}`}>Open</Link>
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 text-sm font-medium">
                <Send className="text-muted-foreground size-4" aria-hidden />
                Submissions
              </div>
              <p className="text-muted-foreground mt-1 text-xs">
                Track review, submission and link verification.
              </p>
            </div>
            <Button asChild variant="outline" size="sm">
              <Link href={`/submissions?campaign_id=${record.id}`}>Open</Link>
            </Button>
          </CardContent>
        </Card>
      </div>

      {stats.data && stats.data.opportunities_total === 0 ? (
        <Card className="mt-4">
          <CardContent className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <Sparkles className="text-muted-foreground mt-0.5 size-4 shrink-0" aria-hidden />
              <div>
                <div className="text-sm font-medium">No opportunities yet</div>
                <p className="text-muted-foreground text-xs">
                  Run discovery to find free directories and listing sites that match this
                  campaign.
                </p>
              </div>
            </div>
            <PermissionGate permission={PERM.PUBLISHER_DISCOVER}>
              <Button asChild size="sm">
                <Link href={`/publishers/discovery?campaign=${record.id}`}>
                  Start discovery
                </Link>
              </Button>
            </PermissionGate>
          </CardContent>
        </Card>
      ) : null}
    </>
  );
}
