"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertCircle, Check, ExternalLink, RefreshCw, Send, X } from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { DetailSkeleton } from "@/components/feedback/loading-state";
import { ErrorState } from "@/components/feedback/error-state";
import { Field } from "@/components/forms/field";
import { FormDialog } from "@/components/forms/form-dialog";
import { DefinitionList } from "@/components/shared/definition-list";
import { PageHeader } from "@/components/shared/page-header";
import { PermissionGate } from "@/components/shared/permission-gate";
import { StatusBadge } from "@/components/shared/status-badge";
import { RejectDialog } from "@/features/opportunities/components/reject-dialog";
import { VerificationTimeline } from "@/features/submissions/components/verification-timeline";
import {
  labelFor,
  SUBMISSION_METHOD_LABELS,
  SUBMISSION_STATUS_LABELS,
} from "@/config/labels";
import { PERM } from "@/config/permissions";
import { useCampaign } from "@/features/campaigns/api/use-campaigns";
import { usePublisher } from "@/features/publishers/api/use-publishers";
import {
  useApproveSubmission,
  useExecuteSubmission,
  useRejectSubmission,
  useSubmission,
  useSubmitForReview,
  useUpdateSubmission,
  useVerifySubmission,
} from "@/features/submissions/api/use-submissions";
import { useOpportunity } from "@/features/opportunities/api/use-opportunities";
import { errorMessage } from "@/lib/api/errors";
import { displayDomain, formatDateTime } from "@/lib/utils/format";
import type { Submission, VerificationEvidence } from "@/types/api";

function readEvidence(submission: Submission): VerificationEvidence {
  const raw = submission.verification_evidence;
  return typeof raw === "object" && raw !== null ? (raw as VerificationEvidence) : {};
}

/**
 * Verification results (spec §30).
 *
 * Rendered from `verification_evidence`, which the backend writes when it
 * fetches the live page.
 */
function VerificationResult({ submission }: { submission: Submission }) {
  const evidence = readEvidence(submission);
  const hasEvidence = Object.keys(evidence).length > 0;

  if (!hasEvidence) {
    return (
      <p className="text-muted-foreground text-sm">
        Not verified yet. Run verification once the listing is live to confirm the link.
      </p>
    );
  }

  return (
    <DefinitionList
      items={[
        {
          label: "Link URL",
          value: evidence.link_url ? (
            <a
              href={evidence.link_url}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:underline"
            >
              {displayDomain(evidence.link_url)}
            </a>
          ) : null,
        },
        { label: "Anchor", value: evidence.anchor_text },
        {
          label: "Link type",
          value: evidence.link_type ? (
            <Badge variant={evidence.link_type === "dofollow" ? "success" : "muted"}>
              {evidence.link_type}
            </Badge>
          ) : null,
        },
        { label: "HTTP status", value: evidence.http_status },
        {
          label: "Link found",
          value:
            evidence.found === undefined
              ? null
              : evidence.found
                ? "Yes"
                : "No",
        },
        {
          label: "Indexed",
          value:
            evidence.indexed === undefined
              ? "Unknown"
              : evidence.indexed
                ? "Yes"
                : "Not yet",
        },
        {
          label: "Last verified",
          value: submission.verified_at
            ? formatDateTime(submission.verified_at)
            : evidence.checked_at
              ? formatDateTime(evidence.checked_at)
              : null,
        },
        { label: "Notes", value: evidence.notes },
      ]}
    />
  );
}

/** Submission review, manual submission and verification (spec §29/§30). */
export function SubmissionDetail({ submissionId }: { submissionId: string }) {
  const submission = useSubmission(submissionId);
  const opportunity = useOpportunity(submission.data?.opportunity_id);
  const publisher = usePublisher(opportunity.data?.publisher_id);
  const campaign = useCampaign(submission.data?.campaign_id);

  const update = useUpdateSubmission(submissionId);
  const submitForReview = useSubmitForReview(submissionId);
  const approve = useApproveSubmission(submissionId);
  const execute = useExecuteSubmission(submissionId);
  const verify = useVerifySubmission(submissionId);
  const reject = useRejectSubmission(submissionId);

  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [anchor, setAnchor] = useState("");
  const [notes, setNotes] = useState("");

  const [markOpen, setMarkOpen] = useState(false);
  const [liveUrl, setLiveUrl] = useState("");
  const [markPublished, setMarkPublished] = useState(false);
  const [rejecting, setRejecting] = useState(false);

  // Adopt server values whenever the record changes, so the editor never shows
  // a stale draft after someone else updated it.
  useEffect(() => {
    const record = submission.data;
    if (!record) return;
    setTitle(record.submitted_title ?? "");
    setDescription(record.submitted_description ?? "");
    setAnchor(record.anchor_text ?? "");
    setNotes(record.notes ?? "");
  }, [submission.data]);

  if (submission.isPending) return <DetailSkeleton />;

  if (submission.error || !submission.data) {
    return (
      <ErrorState
        error={submission.error}
        resource="this submission"
        onRetry={() => void submission.refetch()}
      />
    );
  }

  const record = submission.data;
  const submissionUrl = publisher.data?.submission_url ?? null;

  const canSubmitForReview = record.status === "READY";
  const canApprove = ["READY", "PENDING_APPROVAL"].includes(record.status);
  const canExecute = ["READY", "IN_PROGRESS", "SUBMITTED"].includes(record.status);
  const canVerify = ["SUBMITTED", "PUBLISHED", "VERIFICATION_PENDING"].includes(
    record.status,
  );
  const canReject = !["REJECTED", "VERIFIED", "FAILED"].includes(record.status);
  const canEdit = !["VERIFIED", "PUBLISHED", "REJECTED"].includes(record.status);

  async function handleSave() {
    try {
      await update.mutateAsync({
        submitted_title: title || null,
        submitted_description: description || null,
        anchor_text: anchor || null,
        notes: notes || null,
      });
      toast.success("Submission updated");
      setEditing(false);
    } catch (error) {
      toast.error("Couldn't save changes", { description: errorMessage(error) });
    }
  }

  async function handleApprove() {
    try {
      await approve.mutateAsync({});
      toast.success("Submission approved", {
        description: "It can now be submitted to the publisher.",
      });
    } catch (error) {
      toast.error("Couldn't approve submission", { description: errorMessage(error) });
    }
  }

  async function handleVerify() {
    try {
      const updated = await verify.mutateAsync({ fetch_live: true });
      toast.success("Verification complete", {
        description: `Status is now ${labelFor(SUBMISSION_STATUS_LABELS, updated.status)}.`,
      });
    } catch (error) {
      toast.error("Couldn't verify link", { description: errorMessage(error) });
    }
  }

  return (
    <>
      <PageHeader
        title={record.submitted_title ?? "Submission"}
        description={
          publisher.data
            ? `${publisher.data.name ?? displayDomain(publisher.data.domain)} · ${displayDomain(publisher.data.domain)}`
            : undefined
        }
        badges={<StatusBadge status={record.status} labels={SUBMISSION_STATUS_LABELS} />}
        actions={
          <>
            {canSubmitForReview ? (
              <PermissionGate permission={PERM.SUBMISSION_UPDATE}>
                <Button
                  variant="outline"
                  size="sm"
                  loading={submitForReview.isPending}
                  onClick={() => {
                    void submitForReview
                      .mutateAsync()
                      .then(() => toast.success("Sent for review"))
                      .catch((error: unknown) =>
                        toast.error("Couldn't send for review", {
                          description: errorMessage(error),
                        }),
                      );
                  }}
                >
                  Send for review
                </Button>
              </PermissionGate>
            ) : null}

            {canApprove ? (
              <PermissionGate permission={PERM.SUBMISSION_APPROVE}>
                <Button
                  size="sm"
                  loading={approve.isPending}
                  onClick={() => void handleApprove()}
                >
                  <Check className="size-4" aria-hidden />
                  Approve
                </Button>
              </PermissionGate>
            ) : null}

            {canReject ? (
              <PermissionGate permission={PERM.SUBMISSION_APPROVE}>
                <Button variant="outline" size="sm" onClick={() => setRejecting(true)}>
                  <X className="size-4" aria-hidden />
                  Reject
                </Button>
              </PermissionGate>
            ) : null}
          </>
        }
      />

      {record.failure_reason ? (
        <Alert variant="destructive" className="mb-4">
          <AlertCircle aria-hidden />
          <AlertTitle>
            {record.status === "REJECTED" ? "Rejected" : "Submission failed"}
          </AlertTitle>
          <AlertDescription>{record.failure_reason}</AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between gap-2">
                <CardTitle>Listing content</CardTitle>
                {canEdit ? (
                  <PermissionGate permission={PERM.SUBMISSION_UPDATE}>
                    {editing ? (
                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setEditing(false)}
                          disabled={update.isPending}
                        >
                          Cancel
                        </Button>
                        <Button
                          size="sm"
                          loading={update.isPending}
                          onClick={() => void handleSave()}
                        >
                          Save
                        </Button>
                      </div>
                    ) : (
                      <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
                        Edit
                      </Button>
                    )}
                  </PermissionGate>
                ) : null}
              </div>
            </CardHeader>

            <CardContent className="space-y-4 pt-0">
              {editing ? (
                <>
                  <Field id="submission-title" label="Title">
                    <Input
                      id="submission-title"
                      value={title}
                      onChange={(event) => setTitle(event.target.value)}
                    />
                  </Field>
                  <Field id="submission-description" label="Description">
                    <Textarea
                      id="submission-description"
                      value={description}
                      onChange={(event) => setDescription(event.target.value)}
                      rows={6}
                    />
                  </Field>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field id="submission-anchor" label="Anchor text">
                      <Input
                        id="submission-anchor"
                        value={anchor}
                        onChange={(event) => setAnchor(event.target.value)}
                      />
                    </Field>
                    <Field id="submission-notes" label="Reviewer notes">
                      <Input
                        id="submission-notes"
                        value={notes}
                        onChange={(event) => setNotes(event.target.value)}
                      />
                    </Field>
                  </div>
                </>
              ) : (
                <DefinitionList
                  items={[
                    { label: "Title", value: record.submitted_title },
                    { label: "Category", value: opportunity.data?.category },
                    { label: "Anchor text", value: record.anchor_text },
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
                    { label: "Notes", value: record.notes },
                  ]}
                />
              )}

              {!editing && record.submitted_description ? (
                <div>
                  <div className="text-muted-foreground mb-1 text-xs">Description</div>
                  <p className="text-sm leading-relaxed">{record.submitted_description}</p>
                </div>
              ) : null}
            </CardContent>
          </Card>

          {/*
            Manual submission (spec §29). The user opens the publisher's own
            form, completes it themselves, and comes back to record it. Nothing
            here automates a form or works around a CAPTCHA.
          */}
          {canExecute ? (
            <Card>
              <CardHeader>
                <CardTitle>Submit to publisher</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4 pt-0">
                <ol className="text-muted-foreground list-decimal space-y-1.5 pl-5 text-sm">
                  <li>Open the publisher&apos;s submission page in a new tab.</li>
                  <li>Complete their form using the listing content above.</li>
                  <li>Come back here and record the submission.</li>
                </ol>

                <div className="flex flex-wrap gap-2">
                  {submissionUrl ? (
                    <Button asChild variant="outline" size="sm">
                      <a href={submissionUrl} target="_blank" rel="noopener noreferrer">
                        <ExternalLink className="size-4" aria-hidden />
                        Open publisher
                      </a>
                    </Button>
                  ) : (
                    <p className="text-muted-foreground text-sm">
                      No submission page recorded for this publisher. Open the site and find
                      their listing form.
                    </p>
                  )}

                  <PermissionGate permission={PERM.SUBMISSION_UPDATE}>
                    <Button size="sm" onClick={() => setMarkOpen(true)}>
                      <Send className="size-4" aria-hidden />
                      Submission complete
                    </Button>
                  </PermissionGate>
                </div>
              </CardContent>
            </Card>
          ) : null}

          <Card>
            <CardHeader>
              <div className="flex items-center justify-between gap-2">
                <CardTitle>Verification</CardTitle>
                {canVerify ? (
                  <PermissionGate permission={PERM.SUBMISSION_VERIFY}>
                    <Button
                      variant="outline"
                      size="sm"
                      loading={verify.isPending}
                      onClick={() => void handleVerify()}
                    >
                      <RefreshCw className="size-4" aria-hidden />
                      Verify link
                    </Button>
                  </PermissionGate>
                ) : null}
              </div>
            </CardHeader>
            <CardContent className="pt-0">
              <VerificationResult submission={record} />
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Status</CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              <VerificationTimeline status={record.status} />
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
                    label: "Opportunity",
                    value: (
                      <Link
                        href={`/opportunities/${record.opportunity_id}`}
                        className="hover:underline"
                      >
                        View opportunity
                      </Link>
                    ),
                  },
                  {
                    label: "Publisher",
                    value: publisher.data ? (
                      <Link
                        href={`/publishers/${publisher.data.id}`}
                        className="hover:underline"
                      >
                        {publisher.data.name ?? displayDomain(publisher.data.domain)}
                      </Link>
                    ) : null,
                  },
                  {
                    label: "Method",
                    value: labelFor(SUBMISSION_METHOD_LABELS, record.submission_method),
                  },
                  {
                    label: "Live listing",
                    value: record.submitted_url ? (
                      <a
                        href={record.submitted_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="hover:underline"
                      >
                        Open
                      </a>
                    ) : null,
                  },
                  {
                    label: "Approved",
                    value: record.approved_at ? formatDateTime(record.approved_at) : null,
                  },
                  {
                    label: "Submitted",
                    value: record.submitted_at ? formatDateTime(record.submitted_at) : null,
                  },
                  {
                    label: "Published",
                    value: record.published_at ? formatDateTime(record.published_at) : null,
                  },
                  {
                    label: "Verified",
                    value: record.verified_at ? formatDateTime(record.verified_at) : null,
                  },
                ]}
              />
            </CardContent>
          </Card>
        </div>
      </div>

      <FormDialog
        open={markOpen}
        onOpenChange={setMarkOpen}
        title="Record this submission"
        description="Confirm you've completed the publisher's form. Add the live listing URL if you have it."
        submitLabel="Record submission"
        submitting={execute.isPending}
        onSubmit={(event) => {
          event.preventDefault();
          void execute
            .mutateAsync({
              submitted_url: liveUrl || null,
              mark_published: markPublished,
            })
            .then(() => {
              toast.success("Submission recorded");
              setMarkOpen(false);
              setLiveUrl("");
              setMarkPublished(false);
            })
            .catch((error: unknown) =>
              toast.error("Couldn't record submission", {
                description: errorMessage(error),
              }),
            );
        }}
      >
        <Field
          id="live-url"
          label="Live listing URL"
          hint="Optional. Needed to verify the link automatically."
        >
          <Input
            id="live-url"
            value={liveUrl}
            onChange={(event) => setLiveUrl(event.target.value)}
            placeholder="https://directory.example.com/listing/acme"
          />
        </Field>

        <div className="flex items-start gap-2">
          <Checkbox
            id="mark-published"
            checked={markPublished}
            onCheckedChange={(checked) => setMarkPublished(checked === true)}
          />
          <Label htmlFor="mark-published" className="font-normal">
            The listing is already live
          </Label>
        </div>
      </FormDialog>

      <RejectDialog
        open={rejecting}
        onOpenChange={setRejecting}
        title="Reject this submission?"
        description="It won't be submitted to the publisher. The reason is recorded in the audit trail."
        submitting={reject.isPending}
        onConfirm={async (reason) => {
          try {
            await reject.mutateAsync(reason);
            toast.success("Submission rejected");
            setRejecting(false);
          } catch (error) {
            toast.error("Couldn't reject submission", { description: errorMessage(error) });
          }
        }}
      />
    </>
  );
}
