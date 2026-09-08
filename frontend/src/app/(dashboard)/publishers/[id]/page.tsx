import { PublisherDetail } from "@/features/publishers/components/publisher-detail";

export default async function PublisherDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <PublisherDetail publisherId={id} />;
}
