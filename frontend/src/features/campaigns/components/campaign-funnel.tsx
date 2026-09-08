import Link from "next/link";

import { Progress } from "@/components/ui/progress";
import { formatNumber } from "@/lib/utils/format";
import type { CampaignStats } from "@/types/api";

interface FunnelStage {
  label: string;
  value: number;
  href: string;
  tone: string;
}

/**
 * The campaign funnel (spec §18/§20).
 *
 * Bars are scaled against the widest stage rather than against a fixed 100, so
 * the drop-off between stages is what the eye picks up. Each stage links to the
 * filtered list it represents.
 */
export function CampaignFunnel({
  stats,
  campaignId,
}: {
  stats: CampaignStats;
  campaignId: string;
}) {
  const stages: FunnelStage[] = [
    {
      label: "Discovered",
      value: stats.opportunities_total,
      href: `/opportunities?campaign_id=${campaignId}`,
      tone: "bg-chart-2",
    },
    {
      label: "Qualified",
      value: stats.opportunities_qualified,
      href: `/opportunities?campaign_id=${campaignId}&status=QUALIFIED`,
      tone: "bg-chart-1",
    },
    {
      label: "Selected",
      value: stats.opportunities_ready,
      href: `/opportunities?campaign_id=${campaignId}&status=READY`,
      tone: "bg-chart-1",
    },
    {
      label: "Submitted",
      value: stats.submissions_total,
      href: `/submissions?campaign_id=${campaignId}`,
      tone: "bg-chart-4",
    },
    {
      label: "Published",
      value: stats.submissions_published,
      href: `/submissions?campaign_id=${campaignId}&status=PUBLISHED`,
      tone: "bg-chart-3",
    },
    {
      label: "Verified",
      value: stats.submissions_verified,
      href: `/submissions?campaign_id=${campaignId}&status=VERIFIED`,
      tone: "bg-chart-3",
    },
  ];

  const widest = Math.max(...stages.map((stage) => stage.value), 1);

  return (
    <ol className="space-y-3">
      {stages.map((stage) => (
        <li key={stage.label} className="space-y-1.5">
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <Link href={stage.href} className="hover:underline">
              {stage.label}
            </Link>
            <span className="tabular font-semibold">{formatNumber(stage.value)}</span>
          </div>
          <Progress
            value={(stage.value / widest) * 100}
            className="h-1.5"
            indicatorClassName={stage.tone}
            aria-label={`${stage.label}: ${formatNumber(stage.value)}`}
          />
        </li>
      ))}
    </ol>
  );
}
