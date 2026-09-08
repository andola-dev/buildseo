import { CampaignDetail } from "@/features/campaigns/components/campaign-detail";

export default async function CampaignDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <CampaignDetail campaignId={id} />;
}
