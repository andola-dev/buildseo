"""Publisher qualification.

Turns a candidate domain into a decision. The pieces are separated on purpose:

* the **crawler** gathers evidence (behind a protocol, so a headless browser
  can replace the HTTP fetcher),
* the **metrics provider** adds third-party strength (behind a protocol, so an
  unconfigured vendor scores neutral rather than rejecting everything),
* :mod:`app.publishers.scoring` turns evidence into numbers (pure, so the
  model is reviewable and unit-testable),
* this service persists the outcome and decides the publisher's status.

Scoring weights come from the tenant's own ``settings["scoring"]``, so a
workspace can tune the model without a deployment.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.audit.actions import AuditAction
from app.audit.service import AuditService
from app.config.logging import get_logger
from app.core.enums import PricingType, PublisherStatus
from app.db.session import TenantAwareSession
from app.integrations.crawler.base import CrawlerProvider, SiteSnapshot
from app.integrations.metrics.base import MetricsProvider, SiteMetrics
from app.models.publishers import Publisher
from app.publishers.scoring import (
    PublisherSignals,
    ScoreResult,
    ScoringWeights,
    meets_thresholds,
    score_publisher,
)
from app.repositories.publishers import PublisherRepository
from app.schemas.publishers import ScoreBreakdown

logger = get_logger(__name__)


class QualificationService:
    """Scores a publisher and records the decision."""

    def __init__(
        self,
        *,
        session: TenantAwareSession,
        publishers: PublisherRepository,
        crawler: CrawlerProvider,
        metrics: MetricsProvider,
        audit: AuditService,
        weights: ScoringWeights | None = None,
    ) -> None:
        self._session = session
        self._publishers = publishers
        self._crawler = crawler
        self._metrics = metrics
        self._audit = audit
        self._weights = weights or ScoringWeights()

    async def qualify(
        self,
        publisher: Publisher,
        *,
        fetch_live: bool = True,
        relevance_keywords: tuple[str, ...] = (),
        target_country: str | None = None,
        target_language: str | None = None,
    ) -> tuple[Publisher, ScoreBreakdown]:
        """Gather signals, score, and set the publisher's status."""
        publisher.status = PublisherStatus.QUALIFYING.value
        await self._publishers.flush()

        snapshot: SiteSnapshot | None = None
        metrics: SiteMetrics | None = None
        if fetch_live:
            snapshot = await self._crawler.fetch_site(publisher.website_url)
            metrics = await self._metrics.fetch(publisher.normalized_domain)

        signals = self._build_signals(
            publisher,
            snapshot,
            metrics,
            relevance_keywords=relevance_keywords,
            target_country=target_country,
            target_language=target_language,
        )
        result = score_publisher(signals, self._weights)
        publisher = self._apply(publisher, signals, result, snapshot)
        await self._publishers.flush()

        breakdown = ScoreBreakdown(
            quality_score=result.quality_score,
            relevance_score=result.relevance_score,
            spam_score=result.spam_score,
            authority_score=result.authority_score,
            opportunity_score=result.opportunity_score,
            components=result.components,
            reasons=result.reasons,
            recommended_status=publisher.status,
            eligible_for_submission=publisher.is_submittable,
        )

        await self._audit.record(
            AuditAction.PUBLISHER_QUALIFIED,
            resource_type="publisher",
            resource_id=publisher.id,
            metadata={
                "normalized_domain": publisher.normalized_domain,
                "quality_score": result.quality_score,
                "relevance_score": result.relevance_score,
                "spam_score": result.spam_score,
                "authority_score": result.authority_score,
                "recommended_status": publisher.status,
                "eligible_for_submission": breakdown.eligible_for_submission,
            },
        )
        logger.info(
            "publisher qualified",
            extra={
                "publisher_id": str(publisher.id),
                "status": publisher.status,
                "opportunity_score": result.opportunity_score,
            },
        )
        return publisher, breakdown

    def _build_signals(
        self,
        publisher: Publisher,
        snapshot: SiteSnapshot | None,
        metrics: SiteMetrics | None,
        *,
        relevance_keywords: tuple[str, ...],
        target_country: str | None,
        target_language: str | None,
    ) -> PublisherSignals:
        """Fold crawl output, vendor metrics and stored fields into one bundle.

        When no fresh crawl was requested, the previously stored ``signals``
        are reused so a re-score with new weights does not need another fetch.
        """
        stored = publisher.signals or {}
        if snapshot is None:
            reachable = bool(stored.get("reachable", False))
            tls_valid = bool(stored.get("tls_valid", False))
            has_submission_path = bool(stored.get("has_submission_path", False))
            indexable = bool(stored.get("indexable", True))
            spam_signals = tuple(stored.get("spam_signals") or ())
            outbound_links = stored.get("outbound_links")
            http_status = stored.get("http_status")
            page_text = ""
            paid_detected = bool(stored.get("is_paid_only", False))
        else:
            reachable = snapshot.reachable
            tls_valid = snapshot.tls_valid
            has_submission_path = snapshot.submission_path is not None
            indexable = snapshot.indexable
            spam_signals = snapshot.spam_signals
            outbound_links = snapshot.outbound_link_count
            http_status = snapshot.status_code
            page_text = snapshot.text
            paid_detected = snapshot.paid_listing_detected

        keywords = tuple(
            keyword.strip().lower() for keyword in relevance_keywords if keyword.strip()
        )
        keyword_hits = sum(1 for keyword in keywords if keyword in page_text)

        # Free/paid: an explicit paid signal wins, then a detected free path,
        # then whatever a human already recorded on the row.
        if paid_detected:
            is_free = False
        elif snapshot is not None and snapshot.free_listing_detected:
            is_free = True
        else:
            is_free = publisher.pricing_type == PricingType.FREE.value

        authority = metrics.authority_score if metrics else stored.get("authority_score")
        traffic = metrics.organic_traffic if metrics else stored.get("organic_traffic")
        if metrics and metrics.spam_score is not None and metrics.spam_score >= 50:
            spam_signals = (*spam_signals, "vendor_spam_score_high")

        return PublisherSignals(
            reachable=reachable,
            http_status=http_status,
            tls_valid=tls_valid,
            has_submission_path=has_submission_path,
            is_free=is_free,
            is_paid_only=paid_detected,
            indexable=indexable,
            keyword_hits=keyword_hits,
            keywords_considered=len(keywords),
            category_match=self._category_matches(publisher, page_text),
            country_match=_country_matches(publisher.country, target_country),
            language_match=_language_matches(publisher.language, target_language),
            authority_score=float(authority) if authority is not None else None,
            organic_traffic=int(traffic) if traffic is not None else None,
            spam_signals=spam_signals,
            outbound_links=int(outbound_links) if outbound_links is not None else None,
        )

    @staticmethod
    def _category_matches(publisher: Publisher, page_text: str) -> bool:
        """A recorded category counts; otherwise look for directory language."""
        if publisher.category:
            return True
        if not page_text:
            return False
        return any(
            marker in page_text
            for marker in ("directory", "listings", "business listing", "company profiles")
        )

    def _apply(
        self,
        publisher: Publisher,
        signals: PublisherSignals,
        result: ScoreResult,
        snapshot: SiteSnapshot | None,
    ) -> Publisher:
        """Write scores, evidence and the resulting status onto the row."""
        publisher.quality_score = result.quality_score
        publisher.relevance_score = result.relevance_score
        publisher.spam_score = result.spam_score
        publisher.authority_score = result.authority_score
        if signals.organic_traffic is not None:
            publisher.organic_traffic = signals.organic_traffic
        publisher.signals = {
            **signals.to_dict(),
            "opportunity_score": result.opportunity_score,
            "hard_rejections": list(result.hard_rejections),
            "reasons": result.reasons[:20],
            "scored_at": datetime.now(UTC).isoformat(),
        }
        publisher.last_checked_at = datetime.now(UTC)

        # Pricing is only ever *tightened* automatically. Confirming FREE from a
        # detected submission path is safe; marking something FREE without
        # evidence is not, so an unconfirmed publisher stays UNKNOWN and
        # therefore un-submittable.
        if signals.is_paid_only:
            publisher.pricing_type = PricingType.PAID.value
        elif signals.is_free and signals.has_submission_path:
            publisher.pricing_type = PricingType.FREE.value

        if snapshot is not None and snapshot.submission_path:
            publisher.submission_url = snapshot.submission_path

        if result.is_rejected or not meets_thresholds(result, self._weights):
            publisher.status = PublisherStatus.REJECTED.value
        else:
            publisher.status = PublisherStatus.QUALIFIED.value
        return publisher

    async def qualify_by_id(
        self,
        publisher_id: UUID,
        *,
        fetch_live: bool = True,
        relevance_keywords: tuple[str, ...] = (),
        target_country: str | None = None,
        target_language: str | None = None,
    ) -> tuple[Publisher, ScoreBreakdown]:
        publisher = await self._publishers.get_or_raise(publisher_id, resource="publisher")
        return await self.qualify(
            publisher,
            fetch_live=fetch_live,
            relevance_keywords=relevance_keywords,
            target_country=target_country,
            target_language=target_language,
        )


def _country_matches(publisher_country: str | None, target: str | None) -> bool:
    """A global directory (no country) matches every market."""
    if target is None:
        return True
    if publisher_country is None:
        return True
    return publisher_country.upper() == target.upper()


def _language_matches(publisher_language: str | None, target: str | None) -> bool:
    if target is None or publisher_language is None:
        return True
    return publisher_language.split("-")[0].lower() == target.split("-")[0].lower()
