import { SubmissionDetail } from "@/features/submissions/components/submission-detail";

export default async function SubmissionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <SubmissionDetail submissionId={id} />;
}
