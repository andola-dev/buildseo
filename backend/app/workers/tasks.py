"""Task handlers.

Each handler receives a :class:`TaskEnvelope` and a
:class:`~app.services.factory.ServiceFactory` already bound to the job's tenant
context, so a handler reuses exactly the services an HTTP request would and is
confined by the same RLS policies.

Handlers are intentionally thin: they translate a payload into a service call.
The business logic lives in the services, which is what lets the same operation
run inline (small requests) or deferred (large ones) with identical behaviour.
"""

from __future__ import annotations

from uuid import UUID

from app.config.logging import get_logger
from app.core.enums import PublisherCategory
from app.core.exceptions import ResourceNotFoundError
from app.integrations.discovery.base import DiscoveryQuery
from app.schemas.opportunities import ContentGenerationRequest
from app.schemas.submissions import SubmissionVerifyRequest
from app.services.factory import ServiceFactory
from app.workers.queue import TaskEnvelope
from app.workers.registry import (
    TASK_CONTENT_GENERATE,
    TASK_LINK_MONITOR,
    TASK_OPPORTUNITY_QUALIFY,
    TASK_PUBLISHER_DISCOVERY,
    TASK_PUBLISHER_QUALIFY,
    TASK_SUBMISSION_VERIFY,
    register,
)

logger = get_logger(__name__)


@register(TASK_PUBLISHER_DISCOVERY)
async def run_publisher_discovery(envelope: TaskEnvelope, services: ServiceFactory) -> None:
    """Execute a discovery run that an API call scheduled."""
    payload = envelope.payload
    run_id = UUID(str(payload["run_id"]))
    run = await services.discovery_service.get_run(run_id)

    raw_category = payload.get("category")
    query = DiscoveryQuery(
        keywords=tuple(payload.get("keywords") or ()),
        country=payload.get("country"),
        language=payload.get("language"),
        category=PublisherCategory(raw_category) if raw_category else None,
        limit=int(payload.get("limit", 25)),
    )
    provider = await services.discovery_registry.resolve(str(payload["provider"]))
    await services.discovery_service.execute(run, provider=provider, query=query)


@register(TASK_PUBLISHER_QUALIFY)
async def run_publisher_qualification(envelope: TaskEnvelope, services: ServiceFactory) -> None:
    """Crawl and score one publisher."""
    payload = envelope.payload
    await services.qualification_service.qualify_by_id(
        UUID(str(payload["publisher_id"])),
        fetch_live=bool(payload.get("fetch_live", True)),
        relevance_keywords=tuple(payload.get("relevance_keywords") or ()),
        target_country=payload.get("target_country"),
        target_language=payload.get("target_language"),
    )


@register(TASK_OPPORTUNITY_QUALIFY)
async def run_opportunity_qualification(envelope: TaskEnvelope, services: ServiceFactory) -> None:
    """Score one opportunity from its publisher's qualification."""
    await services.opportunity_service.qualify(UUID(str(envelope.payload["opportunity_id"])))


@register(TASK_CONTENT_GENERATE)
async def run_content_generation(envelope: TaskEnvelope, services: ServiceFactory) -> None:
    """Draft listing content for review."""
    payload = envelope.payload
    request = ContentGenerationRequest(
        tone=payload.get("tone"),
        keywords=list(payload.get("keywords") or []),
        max_description_words=int(payload.get("max_description_words", 120)),
        regenerate=bool(payload.get("regenerate", False)),
    )
    await services.content_service.generate(
        opportunity_id=UUID(str(payload["opportunity_id"])), payload=request
    )


@register(TASK_SUBMISSION_VERIFY)
async def run_submission_verification(envelope: TaskEnvelope, services: ServiceFactory) -> None:
    """Check that a published listing carries the link."""
    payload = envelope.payload
    await services.submission_service.verify(
        UUID(str(payload["submission_id"])),
        payload=SubmissionVerifyRequest(
            published_url=payload.get("published_url"), fetch_live=True
        ),
    )


@register(TASK_LINK_MONITOR)
async def run_link_monitor(envelope: TaskEnvelope, services: ServiceFactory) -> None:
    """Re-verify already-verified submissions to catch removed links.

    Re-uses the verification path rather than a separate code path, so
    "was it ever there?" and "is it still there?" are answered identically.
    """
    payload = envelope.payload
    submission_ids = [UUID(str(value)) for value in (payload.get("submission_ids") or [])]
    for submission_id in submission_ids:
        try:
            await services.submission_service.verify(
                submission_id, payload=SubmissionVerifyRequest(fetch_live=True)
            )
        except ResourceNotFoundError:
            # Deleted between scheduling and running: not an error.
            logger.info(
                "link monitor skipped a missing submission",
                extra={"submission_id": str(submission_id)},
            )
