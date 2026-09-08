"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ExternalLink, Pencil, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DetailSkeleton } from "@/components/feedback/loading-state";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shared/page-header";
import { PermissionGate } from "@/components/shared/permission-gate";
import { StatusBadge } from "@/components/shared/status-badge";
import { DefinitionList } from "@/components/shared/definition-list";
import { CAMPAIGN_STATUS_LABELS, CLIENT_WEBSITE_STATUS_LABELS } from "@/config/labels";
import { PERM } from "@/config/permissions";
import { useCampaigns } from "@/features/campaigns/api/use-campaigns";
import { useWebsite } from "@/features/websites/api/use-websites";
import { WebsiteForm } from "@/features/websites/components/website-form";
import { displayDomain, formatDate, formatNumber } from "@/lib/utils/format";

/** Client website detail, with its campaigns (spec §19). */
export function WebsiteDetail({ websiteId }: { websiteId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const website = useWebsite(websiteId);

  // `?edit=1` opens the form directly, which is what the row action links to.
  const [editing, setEditing] = useState(searchParams.get("edit") === "1");

  const campaigns = useCampaigns({
    page: 1,
    page_size: 10,
    client_website_id: websiteId,
    order: "desc",
    sort: "created_at",
  });

  if (website.isPending) return <DetailSkeleton />;

  if (website.error || !website.data) {
    return (
      <ErrorState
        error={website.error}
        resource="this website"
        onRetry={() => void website.refetch()}
      />
    );
  }

  const record = website.data;

  if (editing) {
    return (
      <div className="mx-auto max-w-3xl">
        <PageHeader title={`Edit ${record.name}`} />
        <WebsiteForm
          website={record}
          onCancel={() => setEditing(false)}
          onDone={() => setEditing(false)}
        />
      </div>
    );
  }

  return (
    <>
      <PageHeader
        title={record.name}
        description={displayDomain(record.website_url)}
        badges={
          <StatusBadge status={record.status} labels={CLIENT_WEBSITE_STATUS_LABELS} />
        }
        actions={
          <>
            <Button asChild variant="outline" size="sm">
              <a href={record.website_url} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="size-4" aria-hidden />
                Open site
              </a>
            </Button>
            <PermissionGate permission={PERM.CLIENT_WEBSITE_UPDATE}>
              <Button size="sm" onClick={() => setEditing(true)}>
                <Pencil className="size-4" aria-hidden />
                Edit
              </Button>
            </PermissionGate>
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle>Details</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <DefinitionList
              items={[
                { label: "Domain", value: record.normalized_domain },
                { label: "Industry", value: record.industry },
                { label: "Target country", value: record.target_country?.toUpperCase() },
                {
                  label: "Other countries",
                  value:
                    record.target_countries && record.target_countries.length > 0
                      ? record.target_countries.join(", ")
                      : null,
                },
                { label: "Language", value: record.target_language },
                { label: "Created", value: formatDate(record.created_at) },
                { label: "Updated", value: formatDate(record.updated_at) },
              ]}
            />
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Description</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            {record.description ? (
              <p className="text-sm leading-relaxed">{record.description}</p>
            ) : (
              <p className="text-muted-foreground text-sm">
                No description yet. A description gives the AI content generator context
                about the business.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <CardTitle>
              Campaigns
              {campaigns.data ? (
                <span className="text-muted-foreground ml-1.5 font-normal">
                  ({formatNumber(campaigns.data.meta.total)})
                </span>
              ) : null}
            </CardTitle>
            <PermissionGate permission={PERM.CAMPAIGN_CREATE}>
              <Button asChild variant="outline" size="sm">
                <Link href={`/campaigns/new?website=${record.id}`}>
                  <Plus className="size-4" aria-hidden />
                  New campaign
                </Link>
              </Button>
            </PermissionGate>
          </div>
        </CardHeader>
        <CardContent className="pt-0">
          {campaigns.isPending ? (
            <p className="text-muted-foreground text-sm">Loading campaigns…</p>
          ) : campaigns.error ? (
            <ErrorState
              error={campaigns.error}
              resource="campaigns"
              onRetry={() => void campaigns.refetch()}
            />
          ) : (campaigns.data?.items.length ?? 0) === 0 ? (
            <EmptyState
              title="No campaigns for this website"
              description="Create a campaign to start discovering free listing opportunities for it."
              action={
                <PermissionGate permission={PERM.CAMPAIGN_CREATE}>
                  <Button
                    size="sm"
                    onClick={() => router.push(`/campaigns/new?website=${record.id}`)}
                  >
                    Create campaign
                  </Button>
                </PermissionGate>
              }
            />
          ) : (
            <ul className="divide-y">
              {campaigns.data?.items.map((campaign) => (
                <li key={campaign.id} className="flex items-center gap-3 py-2.5">
                  <Link
                    href={`/campaigns/${campaign.id}`}
                    className="min-w-0 flex-1 truncate text-sm font-medium hover:underline"
                  >
                    {campaign.name}
                  </Link>
                  <span className="text-muted-foreground text-xs whitespace-nowrap">
                    {campaign.target_link_count
                      ? `${formatNumber(campaign.target_link_count)} links`
                      : "No target"}
                  </span>
                  <StatusBadge status={campaign.status} labels={CAMPAIGN_STATUS_LABELS} />
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </>
  );
}
