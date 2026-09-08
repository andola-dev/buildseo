import { Suspense } from "react";

import { DetailSkeleton } from "@/components/feedback/loading-state";
import { WebsiteDetail } from "@/features/websites/components/website-detail";

export default async function WebsiteDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <Suspense fallback={<DetailSkeleton />}>
      <WebsiteDetail websiteId={id} />
    </Suspense>
  );
}
