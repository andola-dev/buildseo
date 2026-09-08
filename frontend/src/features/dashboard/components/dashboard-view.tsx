"use client";

import Link from "next/link";
import {
  BadgeCheck,
  ClipboardCheck,
  Globe,
  Link2,
  Megaphone,
  Plus,
  Search,
  Send,
  ShieldCheck,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { MetricCardsSkeleton } from "@/components/feedback/loading-state";
import { ActivityFeed, type ActivityItem } from "@/components/shared/activity-feed";
import { FreeListingsBadge } from "@/components/shared/free-listings-badge";
import { MetricCard } from "@/components/shared/metric-card";
import { PageHeader } from "@/components/shared/page-header";
import { PermissionGate } from "@/components/shared/permission-gate";
import { ProgressCard } from "@/components/shared/progress-card";
import { PERM } from "@/config/permissions";
import { CampaignFunnel } from "@/features/campaigns/components/campaign-funnel";
import { useCampaignStats } from "@/features/campaigns/api/use-campaigns";
import {
  useCampaignProgress,
  useDashboardSummary,
  useRecentActivity,
} from "@/features/dashboard/api/use-dashboard";
import { usePermissions } from "@/lib/permissions/use-permissions";
import { useAuth } from "@/lib/auth/auth-provider";
import { useTenant } from "@/lib/tenant/use-tenant";
import { formatNumber, userDisplayName } from "@/lib/utils/format";
import { humanizeEnum } from "@/config/labels";

/**
 * Map an audit action to an icon and tone.
 *
 * Audit actions are dotted strings such as `submission.approve`; matching on
 * the verb keeps this working when new resources are added.
 */
function activityPresentation(action: string): { icon: LucideIcon; tone: ActivityItem["tone"] } {
  if (action.includes("qualif")) return { icon: BadgeCheck, tone: "success" };
  if (action.includes("verify")) return { icon: ShieldCheck, tone: "success" };
  if (action.includes("approve") || action.includes("select"))
    return { icon: ClipboardCheck, tone: "success" };
  if (action.includes("reject") || action.includes("delete"))
    return { icon: Link2, tone: "danger" };
  if (action.includes("submission")) return { icon: Send, tone: "default" };
  if (action.includes("discover")) return { icon: Search, tone: "default" };
  if (action.includes("campaign")) return { icon: Megaphone, tone: "default" };
  if (action.includes("publisher")) return { icon: Globe, tone: "default" };
  return { icon: Link2, tone: "default" };
}

/** Funnel for one campaign, loaded only for the campaign being shown. */
function CampaignFunnelCard({ campaignId }: { campaignId: string }) {
  const stats = useCampaignStats(campaignId);

  if (stats.isPending) {
    return <p className="text-muted-foreground text-sm">Loading campaign performance…</p>;
  }

  if (stats.error || !stats.data) {
    return (
      <ErrorState
        error={stats.error}
        resource="campaign performance"
        onRetry={() => void stats.refetch()}
      />
    );
  }

  return <CampaignFunnel stats={stats.data} campaignId={campaignId} />;
}

/** The dashboard (spec §18). */
export function DashboardView() {
  const { user } = useAuth();
  const { activeTenant } = useTenant();
  const { can } = usePermissions();

  const { summary, isPending, error, refetch } = useDashboardSummary();
  const progress = useCampaignProgress();
  const activity = useRecentActivity(can(PERM.AUDIT_READ));

  const firstName = userDisplayName(user).split(" ")[0] ?? "there";
  const leadCampaign = progress.data?.items[0];

  const activityItems: ActivityItem[] = (activity.data?.items ?? []).map((entry) => {
    const { icon, tone } = activityPresentation(entry.action);
    return {
      id: entry.id,
      icon,
      tone,
      title: humanizeEnum(entry.action.replace(/\./g, " ")),
      detail: entry.resource_type
        ? `${humanizeEnum(entry.resource_type)}${entry.resource_id ? ` · ${entry.resource_id.slice(0, 8)}` : ""}`
        : null,
      timestamp: entry.created_at,
    };
  });

  return (
    <>
      <PageHeader
        title={`Welcome back, ${firstName}`}
        description={
          activeTenant
            ? `Free listing link building for ${activeTenant.tenant_name}.`
            : undefined
        }
        badges={<FreeListingsBadge />}
        actions={
          <>
            <PermissionGate permission={PERM.PUBLISHER_DISCOVER}>
              <Button asChild variant="outline" size="sm">
                <Link href="/publishers/discovery">
                  <Search className="size-4" aria-hidden />
                  Discovery
                </Link>
              </Button>
            </PermissionGate>
            <PermissionGate permission={PERM.CAMPAIGN_CREATE}>
              <Button asChild size="sm">
                <Link href="/campaigns/new">
                  <Plus className="size-4" aria-hidden />
                  New campaign
                </Link>
              </Button>
            </PermissionGate>
          </>
        }
      />

      {isPending ? (
        <MetricCardsSkeleton />
      ) : error ? (
        <Card>
          <ErrorState
            error={error}
            resource="your dashboard"
            onRetry={() => void refetch()}
          />
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          <MetricCard
            label="Active campaigns"
            value={formatNumber(summary.activeCampaigns)}
            icon={Megaphone}
            href="/campaigns?status=ACTIVE"
          />
          <MetricCard
            label="Qualified publishers"
            value={formatNumber(summary.qualifiedPublishers)}
            icon={Globe}
            href="/publishers?status=QUALIFIED"
          />
          <MetricCard
            label="Available opportunities"
            value={formatNumber(summary.availableOpportunities)}
            icon={Link2}
            href="/opportunities?status=QUALIFIED"
          />
          <MetricCard
            label="Links submitted"
            value={formatNumber(summary.linksSubmitted)}
            icon={Send}
            href="/submissions?status=SUBMITTED"
          />
          <MetricCard
            label="Links published"
            value={formatNumber(summary.linksPublished)}
            icon={BadgeCheck}
            hint={`${formatNumber(summary.linksVerified)} verified`}
            href="/submissions?status=PUBLISHED"
          />
        </div>
      )}

      {summary.pendingReview > 0 ? (
        <Card className="mt-4">
          <CardContent className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <ClipboardCheck className="text-warning mt-0.5 size-4 shrink-0" aria-hidden />
              <div>
                <div className="text-sm font-medium">
                  {formatNumber(summary.pendingReview)} submission
                  {summary.pendingReview === 1 ? "" : "s"} awaiting approval
                </div>
                <p className="text-muted-foreground text-xs">
                  Approval is the human-in-the-loop gate before anything is submitted.
                </p>
              </div>
            </div>
            <Button asChild size="sm">
              <Link href="/submissions?status=PENDING_APPROVAL">Review queue</Link>
            </Button>
          </CardContent>
        </Card>
      ) : null}

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between gap-2">
              <CardTitle>Campaign performance</CardTitle>
              {leadCampaign ? (
                <Link
                  href={`/campaigns/${leadCampaign.id}`}
                  className="text-muted-foreground text-xs hover:underline"
                >
                  {leadCampaign.name}
                </Link>
              ) : null}
            </div>
          </CardHeader>
          <CardContent className="pt-0">
            {progress.isPending ? (
              <p className="text-muted-foreground text-sm">Loading campaigns…</p>
            ) : progress.error ? (
              <ErrorState
                error={progress.error}
                resource="campaigns"
                onRetry={() => void progress.refetch()}
              />
            ) : leadCampaign ? (
              <CampaignFunnelCard campaignId={leadCampaign.id} />
            ) : (
              <EmptyState
                icon={Megaphone}
                title="No active campaigns"
                description="Create a campaign to start discovering free listing opportunities."
                action={
                  <PermissionGate permission={PERM.CAMPAIGN_CREATE}>
                    <Button asChild size="sm">
                      <Link href="/campaigns/new">Create campaign</Link>
                    </Button>
                  </PermissionGate>
                }
              />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent activity</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            {!can(PERM.AUDIT_READ) ? (
              <p className="text-muted-foreground text-sm">
                Recent activity comes from the audit trail, which your role can&apos;t view.
              </p>
            ) : activity.isPending ? (
              <p className="text-muted-foreground text-sm">Loading activity…</p>
            ) : activity.error ? (
              <ErrorState
                error={activity.error}
                resource="recent activity"
                onRetry={() => void activity.refetch()}
              />
            ) : activityItems.length === 0 ? (
              <EmptyState
                title="No activity yet"
                description="Discovery, qualification and submission events appear here."
              />
            ) : (
              <ActivityFeed items={activityItems} />
            )}
          </CardContent>
        </Card>
      </div>

      {(progress.data?.items.length ?? 0) > 0 ? (
        <Card className="mt-4">
          <CardHeader>
            <CardTitle>Campaign progress</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 pt-0">
            {progress.data?.items.map((campaign) => (
              <CampaignProgressRow key={campaign.id} campaignId={campaign.id} name={campaign.name} target={campaign.target_link_count} />
            ))}
          </CardContent>
        </Card>
      ) : null}
    </>
  );
}

/** One campaign's published-link progress. */
function CampaignProgressRow({
  campaignId,
  name,
  target,
}: {
  campaignId: string;
  name: string;
  target: number | null | undefined;
}) {
  const stats = useCampaignStats(campaignId);

  return (
    <ProgressCard
      title={name}
      href={`/campaigns/${campaignId}`}
      current={stats.data?.submissions_published ?? 0}
      target={stats.data?.target_link_count ?? target ?? null}
    />
  );
}
