"""Submission and generated-content data access."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.sql.elements import ColumnElement

from app.core.enums import ContentStatus, SubmissionStatus
from app.models.submissions import GeneratedContent, Submission
from app.repositories.base import TenantRepository


class SubmissionRepository(TenantRepository[Submission]):
    model = Submission
    sortable_fields = frozenset(
        {
            "created_at",
            "updated_at",
            "status",
            "submitted_at",
            "published_at",
            "verified_at",
            "approved_at",
        }
    )
    default_sort = "created_at"

    async def get_live_for_opportunity(self, opportunity_id: UUID) -> Submission | None:
        """The non-terminal submission for an opportunity, if any.

        Mirrors the partial unique index: terminal rows are excluded, so a
        FAILED or REJECTED attempt does not block a retry.
        """
        result = await self.session.execute(
            self._select().where(
                Submission.opportunity_id == opportunity_id,
                Submission.status.notin_(list(SubmissionStatus.terminal_values())),
            )
        )
        return result.scalar_one_or_none()

    async def list_awaiting_approval(self, *, limit: int = 50) -> list[Submission]:
        """The human review queue.

        Backed by ``ix_submissions_tenant_id_awaiting_review``.
        """
        result = await self.session.execute(
            self._select()
            .where(Submission.status == SubmissionStatus.PENDING_APPROVAL.value)
            .order_by(Submission.updated_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    def build_filters(
        self,
        *,
        status: str | None = None,
        campaign_id: UUID | None = None,
        opportunity_id: UUID | None = None,
        submission_method: str | None = None,
        search: str | None = None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []
        if status:
            filters.append(Submission.status == status)
        if campaign_id:
            filters.append(Submission.campaign_id == campaign_id)
        if opportunity_id:
            filters.append(Submission.opportunity_id == opportunity_id)
        if submission_method:
            filters.append(Submission.submission_method == submission_method)
        if search:
            filters.append(Submission.target_url.ilike(f"%{search.strip()}%"))
        return filters


class GeneratedContentRepository(TenantRepository[GeneratedContent]):
    model = GeneratedContent
    sortable_fields = frozenset({"created_at", "updated_at", "content_status"})
    default_sort = "created_at"

    async def list_for_opportunity(self, opportunity_id: UUID) -> list[GeneratedContent]:
        """Every draft for an opportunity, newest first.

        History is kept rather than overwritten: superseded drafts are what
        make an approval auditable after the fact.
        """
        result = await self.session.execute(
            self._select()
            .where(GeneratedContent.opportunity_id == opportunity_id)
            .order_by(GeneratedContent.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_approved_for_opportunity(self, opportunity_id: UUID) -> GeneratedContent | None:
        """The reviewed draft a submission is allowed to use."""
        result = await self.session.execute(
            self._select()
            .where(
                GeneratedContent.opportunity_id == opportunity_id,
                GeneratedContent.content_status == ContentStatus.APPROVED.value,
            )
            .order_by(GeneratedContent.reviewed_at.desc().nullslast())
        )
        return result.scalars().first()

    async def supersede_drafts(self, opportunity_id: UUID) -> None:
        """Mark existing non-terminal drafts superseded before adding a new one."""
        for content in await self.list_for_opportunity(opportunity_id):
            if content.content_status in (
                ContentStatus.DRAFT.value,
                ContentStatus.PENDING_REVIEW.value,
            ):
                content.content_status = ContentStatus.SUPERSEDED.value
        await self.session.flush()
