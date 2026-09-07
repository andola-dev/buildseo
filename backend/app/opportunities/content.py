"""AI listing-content generation and human review.

The human-in-the-loop pipeline:

    AI drafts -> stored -> a person reviews (and may edit) -> approved
    -> a submission may use it

Content is **always persisted before** it can be submitted, with the provider,
model and timestamp that produced it. That is what makes the workflow
auditable: a reviewer approves a specific artifact, and afterwards anyone can
see exactly what was generated, by what, who signed it off, and what they
changed.

Superseded drafts are kept rather than overwritten, so an approval decision
stays inspectable after a regeneration.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.audit.actions import AuditAction
from app.audit.service import AuditService
from app.config.logging import get_logger
from app.core.enums import AiOperation, AiPurpose, ContentStatus
from app.core.exceptions import BusinessRuleError, ProviderError, ResourceNotFoundError
from app.db.session import TenantAwareSession
from app.integrations.ai.base import GenerationRequest
from app.integrations.ai.factory import AIProviderFactory
from app.integrations.ai.usage import AiUsageService
from app.models.client_websites import ClientWebsite
from app.models.publishers import Publisher
from app.models.submissions import GeneratedContent
from app.repositories.campaigns import CampaignRepository
from app.repositories.client_websites import ClientWebsiteRepository
from app.repositories.opportunities import OpportunityRepository
from app.repositories.submissions import GeneratedContentRepository
from app.schemas.opportunities import ContentGenerationRequest, ContentReviewRequest

logger = get_logger(__name__)

_SYSTEM_PROMPT = """You write directory listing copy for a link-building platform.

Write accurate, useful copy for a legitimate business directory submission. \
Follow the directory's category and the client's actual business. Do not \
invent facts, awards, credentials, customer counts or claims that are not in \
the brief. Do not keyword-stuff. Write as a person describing a business, not \
as an SEO tool.

Reply with a single JSON object containing exactly these keys:
  listing_title          - up to 70 characters
  short_description      - one sentence, up to 160 characters
  long_description       - 2-4 sentences
  business_description   - a neutral one-paragraph description of the business
  category_suggestion    - the directory category that fits best
  anchor_suggestion      - natural anchor text, usually the brand name
  tags                   - array of up to 8 short topical tags
"""

#: The fields a reviewer may edit. Anything else in an edit payload is
#: dropped, so a review cannot introduce arbitrary keys into the stored draft.
EDITABLE_FIELDS: frozenset[str] = frozenset(
    {
        "listing_title",
        "short_description",
        "long_description",
        "business_description",
        "category_suggestion",
        "anchor_suggestion",
        "tags",
    }
)


class ContentGenerationService:
    """Generates, stores and reviews AI listing drafts."""

    def __init__(
        self,
        *,
        session: TenantAwareSession,
        contents: GeneratedContentRepository,
        opportunities: OpportunityRepository,
        campaigns: CampaignRepository,
        client_websites: ClientWebsiteRepository,
        ai_factory: AIProviderFactory,
        usage: AiUsageService,
        audit: AuditService,
    ) -> None:
        self._session = session
        self._contents = contents
        self._opportunities = opportunities
        self._campaigns = campaigns
        self._client_websites = client_websites
        self._ai_factory = ai_factory
        self._usage = usage
        self._audit = audit

    # ------------------------------------------------------------ generate --

    async def generate(
        self, *, opportunity_id: UUID, payload: ContentGenerationRequest
    ) -> GeneratedContent:
        """Draft listing copy for an opportunity and store it for review."""
        pair = await self._opportunities.get_with_publisher(opportunity_id)
        if pair is None:
            raise ResourceNotFoundError.for_resource("opportunity", opportunity_id)
        opportunity, publisher = pair

        campaign = await self._campaigns.get(opportunity.campaign_id)
        if campaign is None:
            raise ResourceNotFoundError.for_resource("campaign", opportunity.campaign_id)
        website = await self._client_websites.get(campaign.client_website_id)
        if website is None:
            raise ResourceNotFoundError.for_resource("client_website", campaign.client_website_id)

        if not payload.regenerate:
            existing = await self._contents.get_approved_for_opportunity(opportunity_id)
            if existing is not None:
                # An approved draft already exists; regenerating would discard
                # a human decision, so the caller must ask explicitly.
                raise BusinessRuleError(
                    "This opportunity already has approved content. "
                    "Pass regenerate=true to supersede it.",
                    code="CONTENT_ALREADY_APPROVED",
                    details={"content_id": str(existing.id)},
                )

        resolved = await self._ai_factory.for_purpose(AiPurpose.CONTENT_GENERATION)
        prompt = self._build_prompt(website, publisher, opportunity.target_url, payload)

        try:
            result = await resolved.provider.generate(
                GenerationRequest(
                    prompt=prompt,
                    model=resolved.model,
                    system=_SYSTEM_PROMPT,
                    max_tokens=int(resolved.config.parameters.get("max_tokens", 1500)),
                    temperature=float(resolved.config.parameters.get("temperature", 0.5)),
                    json_output=True,
                    extra=_provider_extra(resolved.config.parameters),
                )
            )
        except ProviderError as exc:
            # Failures are accounted for too: an expired key shows up as a
            # spike of failures rather than as silence.
            await self._usage.record_failure(
                provider=resolved.provider_key,
                model=resolved.model,
                operation=AiOperation.GENERATE,
                error_code=exc.code,
                purpose=AiPurpose.CONTENT_GENERATION.value,
            )
            raise

        await self._usage.record_generation(result, purpose=AiPurpose.CONTENT_GENERATION.value)

        fields = _parse_content(result.text)
        fields["target_url"] = opportunity.target_url

        # Existing drafts become SUPERSEDED rather than being deleted, so the
        # history behind an approval stays inspectable.
        await self._contents.supersede_drafts(opportunity_id)

        content = self._contents.new(
            opportunity_id=opportunity_id,
            content_status=ContentStatus.PENDING_REVIEW.value,
            generated_content=fields,
            ai_provider=result.provider,
            ai_model=result.model,
            generation_timestamp=datetime.now(UTC),
        )
        await self._contents.flush()

        await self._audit.record(
            AuditAction.CONTENT_GENERATED,
            resource_type="generated_content",
            resource_id=content.id,
            metadata={
                "opportunity_id": str(opportunity_id),
                "ai_provider": result.provider,
                "ai_model": result.model,
                "content_id": str(content.id),
                "field_count": len(fields),
            },
        )
        logger.info(
            "listing content generated",
            extra={
                "opportunity_id": str(opportunity_id),
                "ai_provider": result.provider,
                "ai_model": result.model,
            },
        )
        return content

    @staticmethod
    def _build_prompt(
        website: ClientWebsite,
        publisher: Publisher,
        target_url: str,
        payload: ContentGenerationRequest,
    ) -> str:
        """Assemble the brief. Only facts already held about the client."""
        lines = [
            "Business to list:",
            f"- Name: {website.name}",
            f"- Website: {website.website_url}",
            f"- URL to list: {target_url}",
        ]
        if website.industry:
            lines.append(f"- Industry: {website.industry}")
        if website.description:
            lines.append(f"- About: {website.description}")
        if website.target_country:
            lines.append(f"- Primary market: {website.target_country}")
        if website.target_language:
            lines.append(f"- Language: {website.target_language}")

        lines.append("")
        lines.append("Directory it is being submitted to:")
        lines.append(f"- Name: {publisher.name or publisher.normalized_domain}")
        if publisher.category:
            lines.append(f"- Category: {publisher.category}")
        if publisher.description:
            lines.append(f"- About: {publisher.description}")
        if publisher.country:
            lines.append(f"- Country focus: {publisher.country}")

        lines.append("")
        lines.append("Requirements:")
        lines.append(f"- long_description must be at most {payload.max_description_words} words.")
        if payload.tone:
            lines.append(f"- Tone: {payload.tone}.")
        if payload.keywords:
            lines.append(
                "- Work these terms in only where they read naturally: "
                f"{', '.join(payload.keywords)}."
            )
        if not payload.include_short_description:
            lines.append("- short_description may be an empty string.")
        if not payload.include_long_description:
            lines.append("- long_description may be an empty string.")
        return "\n".join(lines)

    # -------------------------------------------------------------- review --

    async def list_for_opportunity(self, opportunity_id: UUID) -> list[GeneratedContent]:
        return await self._contents.list_for_opportunity(opportunity_id)

    async def review(
        self, *, content_id: UUID, payload: ContentReviewRequest, reviewer_id: UUID
    ) -> GeneratedContent:
        """Record a human decision on a draft."""
        content = await self._contents.get_or_raise(content_id, resource="generated_content")
        if content.content_status in (
            ContentStatus.APPROVED.value,
            ContentStatus.REJECTED.value,
        ):
            raise BusinessRuleError(
                "This draft has already been reviewed",
                code="CONTENT_ALREADY_REVIEWED",
                details={"content_status": content.content_status},
            )

        edited = False
        if payload.edited_content:
            # Allow-listed: a review may correct the copy, not inject new keys.
            clean = {
                key: value
                for key, value in payload.edited_content.items()
                if key in EDITABLE_FIELDS
            }
            if clean:
                content.generated_content = {**content.generated_content, **clean}
                edited = True

        content.content_status = payload.decision.value
        content.reviewed_by_user_id = reviewer_id
        content.reviewed_at = datetime.now(UTC)
        content.review_notes = payload.notes
        await self._contents.flush()

        await self._audit.record(
            AuditAction.CONTENT_REVIEWED,
            resource_type="generated_content",
            resource_id=content.id,
            user_id=reviewer_id,
            metadata={
                "content_id": str(content.id),
                "decision": payload.decision.value,
                "edited": edited,
            },
        )
        return content

    async def approved_for_opportunity(self, opportunity_id: UUID) -> GeneratedContent | None:
        return await self._contents.get_approved_for_opportunity(opportunity_id)


def _provider_extra(parameters: dict[str, Any]) -> dict[str, Any]:
    """Pass through provider parameters, minus the ones handled explicitly."""
    handled = {"max_tokens", "temperature", "base_url"}
    return {key: value for key, value in parameters.items() if key not in handled}


def _parse_content(text: str) -> dict[str, Any]:
    """Parse the model's JSON reply into the stored field set.

    A model can wrap JSON in prose or a code fence, so the object is located
    rather than assumed. Unknown keys are dropped and every value coerced, so
    a malformed reply cannot write arbitrary structure into the row.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
    start, end = stripped.find("{"), stripped.rfind("}")
    if start == -1 or end <= start:
        raise ProviderError(
            "The AI provider did not return JSON listing content",
            code="CONTENT_NOT_JSON",
        )
    try:
        parsed = json.loads(stripped[start : end + 1])
    except ValueError as exc:
        raise ProviderError(
            "The AI provider returned malformed JSON listing content",
            code="CONTENT_NOT_JSON",
        ) from exc
    if not isinstance(parsed, dict):
        raise ProviderError(
            "The AI provider returned an unexpected content shape",
            code="CONTENT_NOT_JSON",
        )

    fields: dict[str, Any] = {}
    for key in EDITABLE_FIELDS:
        value = parsed.get(key)
        if key == "tags":
            fields[key] = [str(tag)[:60] for tag in value][:8] if isinstance(value, list) else []
        elif value is not None:
            fields[key] = str(value).strip()[:4000]
        else:
            fields[key] = ""

    if not fields.get("listing_title"):
        raise ProviderError(
            "The AI provider returned no listing title",
            code="CONTENT_INCOMPLETE",
        )
    return fields
