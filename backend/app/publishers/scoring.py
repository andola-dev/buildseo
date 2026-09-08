"""Publisher qualification scoring.

Pure functions over a signal bundle. Nothing here touches the database, HTTP or
a provider, which is what makes the scoring model reviewable and testable in
isolation — and what lets the weights be tuned per tenant without any risk to
the rest of the system.

The four component scores are deliberately separate rather than collapsed into
one number:

* ``quality`` — is this a real, usable, reachable directory?
* ``relevance`` — does it match the campaign's topic, country and language?
* ``spam`` — how many negative signals does it show? (higher is worse)
* ``authority`` — third-party strength metrics, when a tenant has a provider
  configured for them.

``opportunity_score`` is the weighted combination used for ranking. Keeping the
parts visible means a user can see *why* something scored as it did, which is
the difference between a score they trust and a number they ignore.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Self

#: Signals that mark a site as unsuitable regardless of anything else.
HARD_REJECT_REASONS = frozenset(
    {
        "unreachable",
        "paid_only",
        "no_submission_path",
        "link_scheme_detected",
    }
)


@dataclass(frozen=True, slots=True)
class ScoringWeights:
    """Tunable scoring configuration.

    Loaded from tenant settings (``settings["scoring"]``) so a tenant can bias
    toward, say, relevance over authority without a deployment. Every field has
    a defensible default, and :meth:`from_mapping` ignores unknown keys so an
    older stored configuration keeps working.
    """

    # component weights for the combined opportunity score
    quality_weight: float = 0.35
    relevance_weight: float = 0.30
    authority_weight: float = 0.20
    #: Subtracted, not added: spam is a penalty.
    spam_weight: float = 0.15

    # quality sub-signals
    reachable_points: float = 30.0
    tls_points: float = 10.0
    submission_path_points: float = 25.0
    free_listing_points: float = 20.0
    indexable_points: float = 15.0

    # relevance sub-signals
    keyword_match_points: float = 12.0
    max_keyword_points: float = 60.0
    category_match_points: float = 20.0
    country_match_points: float = 12.0
    language_match_points: float = 8.0

    # spam sub-signals (each detected signal adds this penalty)
    spam_signal_points: float = 22.0
    excessive_outbound_links_points: float = 18.0

    # decision thresholds
    min_quality_score: float = 45.0
    max_spam_score: float = 50.0
    min_opportunity_score: float = 40.0

    #: When a tenant has no metrics provider configured, authority is unknown.
    #: A neutral midpoint is used rather than 0, so an absent integration does
    #: not silently reject every publisher.
    default_authority_score: float = 50.0

    @classmethod
    def from_mapping(cls, values: dict[str, Any] | None) -> Self:
        """Build from stored settings, ignoring unknown or invalid entries."""
        if not values:
            return cls()
        known = set(cls.__dataclass_fields__)
        clean: dict[str, float] = {}
        for key, value in values.items():
            if key in known and isinstance(value, (int, float)) and not isinstance(value, bool):
                clean[key] = float(value)
        return cls(**clean)


@dataclass(frozen=True, slots=True)
class PublisherSignals:
    """Evidence gathered about a publisher.

    Every field is optional/defaulted so a partially-crawled site can still be
    scored; missing evidence lowers a score rather than raising an error.
    """

    reachable: bool = False
    http_status: int | None = None
    tls_valid: bool = False
    #: A discoverable "add your listing" / "submit site" path.
    has_submission_path: bool = False
    #: Publisher is free to list on (``pricing_type == FREE``).
    is_free: bool = False
    #: Explicitly paid-only; a hard reject for this platform.
    is_paid_only: bool = False
    #: Not blocked by robots/meta-noindex, so a link there can actually count.
    indexable: bool = True
    #: Campaign keywords found in the site's text.
    keyword_hits: int = 0
    keywords_considered: int = 0
    category_match: bool = False
    country_match: bool = False
    language_match: bool = False
    #: Third-party metrics, when a provider is configured.
    authority_score: float | None = None
    organic_traffic: int | None = None
    #: Named negative signals, e.g. "paid_links_offered", "adult_content".
    spam_signals: tuple[str, ...] = ()
    outbound_links: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialisable form stored in ``publishers.signals``."""
        return {
            "reachable": self.reachable,
            "http_status": self.http_status,
            "tls_valid": self.tls_valid,
            "has_submission_path": self.has_submission_path,
            "is_free": self.is_free,
            "is_paid_only": self.is_paid_only,
            "indexable": self.indexable,
            "keyword_hits": self.keyword_hits,
            "keywords_considered": self.keywords_considered,
            "category_match": self.category_match,
            "country_match": self.country_match,
            "language_match": self.language_match,
            "authority_score": self.authority_score,
            "organic_traffic": self.organic_traffic,
            "spam_signals": list(self.spam_signals),
            "outbound_links": self.outbound_links,
        }


@dataclass(frozen=True, slots=True)
class ScoreResult:
    """Scores plus the reasoning behind them."""

    quality_score: float
    relevance_score: float
    spam_score: float
    authority_score: float
    opportunity_score: float
    components: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    hard_rejections: tuple[str, ...] = ()

    @property
    def is_rejected(self) -> bool:
        return bool(self.hard_rejections)


def _clamp(value: float) -> float:
    """Constrain to the 0-100 range the database CHECK constraints require."""
    return max(0.0, min(100.0, round(value, 2)))


def score_quality(signals: PublisherSignals, weights: ScoringWeights) -> tuple[float, list[str]]:
    """Is this a real, reachable, usable free directory?"""
    total = 0.0
    reasons: list[str] = []

    if signals.reachable:
        total += weights.reachable_points
    else:
        reasons.append("Site did not respond successfully")
    if signals.tls_valid:
        total += weights.tls_points
    else:
        reasons.append("No valid HTTPS certificate")
    if signals.has_submission_path:
        total += weights.submission_path_points
    else:
        reasons.append("No listing submission path found")
    if signals.is_free:
        total += weights.free_listing_points
    elif signals.is_paid_only:
        reasons.append("Listing appears to require payment")
    else:
        reasons.append("Free listing availability unconfirmed")
    if signals.indexable:
        total += weights.indexable_points
    else:
        reasons.append("Site blocks indexing, so a listing there would carry no value")

    return _clamp(total), reasons


def score_relevance(signals: PublisherSignals, weights: ScoringWeights) -> tuple[float, list[str]]:
    """Does the directory match the campaign's topic and market?"""
    total = 0.0
    reasons: list[str] = []

    keyword_points = min(
        signals.keyword_hits * weights.keyword_match_points, weights.max_keyword_points
    )
    total += keyword_points
    if signals.keywords_considered and not signals.keyword_hits:
        reasons.append("None of the campaign keywords appear on the site")

    if signals.category_match:
        total += weights.category_match_points
    else:
        reasons.append("Directory category does not match the campaign")
    if signals.country_match:
        total += weights.country_match_points
    if signals.language_match:
        total += weights.language_match_points

    return _clamp(total), reasons


def score_spam(signals: PublisherSignals, weights: ScoringWeights) -> tuple[float, list[str]]:
    """How many negative signals does the site show? Higher is worse."""
    total = 0.0
    reasons: list[str] = []

    for signal in signals.spam_signals:
        total += weights.spam_signal_points
        reasons.append(f"Spam signal detected: {signal.replace('_', ' ')}")

    # A directory page that is nothing but outbound links is a link farm, not a
    # directory anyone reads.
    if signals.outbound_links is not None and signals.outbound_links > 300:
        total += weights.excessive_outbound_links_points
        reasons.append(f"Unusually high outbound link count ({signals.outbound_links})")

    return _clamp(total), reasons


def score_authority(signals: PublisherSignals, weights: ScoringWeights) -> tuple[float, list[str]]:
    """Third-party strength, or a neutral default when unmeasured."""
    if signals.authority_score is None:
        return (
            _clamp(weights.default_authority_score),
            ["Authority unknown: no SEO metrics provider configured"],
        )
    return _clamp(signals.authority_score), []


def find_hard_rejections(signals: PublisherSignals) -> tuple[str, ...]:
    """Disqualifying findings, independent of any weighting.

    ``paid_only`` is here because of the platform's core rule: a paid
    placement is out of scope, so no combination of other signals should let it
    through.
    """
    rejections: list[str] = []
    if not signals.reachable:
        rejections.append("unreachable")
    if signals.is_paid_only:
        rejections.append("paid_only")
    if not signals.has_submission_path:
        rejections.append("no_submission_path")
    if any(
        signal in {"paid_links_offered", "link_scheme", "pbn_footprint"}
        for signal in signals.spam_signals
    ):
        rejections.append("link_scheme_detected")
    return tuple(rejections)


def score_publisher(
    signals: PublisherSignals, weights: ScoringWeights | None = None
) -> ScoreResult:
    """Compute every component score and the combined opportunity score."""
    active = weights or ScoringWeights()

    quality, quality_reasons = score_quality(signals, active)
    relevance, relevance_reasons = score_relevance(signals, active)
    spam, spam_reasons = score_spam(signals, active)
    authority, authority_reasons = score_authority(signals, active)

    # The three positive components are averaged by their own weight mass, so
    # the result stays on a 0-100 scale however a tenant has tuned them.
    # Spam is then subtracted: its weight is a penalty share, not a
    # contribution, which is why it is excluded from the normalising mass.
    positive_mass = active.quality_weight + active.relevance_weight + active.authority_weight
    if positive_mass <= 0:
        raise ValueError("quality, relevance and authority weights must sum to a positive value")
    weighted_positive = (
        quality * active.quality_weight
        + relevance * active.relevance_weight
        + authority * active.authority_weight
    ) / positive_mass
    opportunity = _clamp(weighted_positive - spam * active.spam_weight)

    return ScoreResult(
        quality_score=quality,
        relevance_score=relevance,
        spam_score=spam,
        authority_score=authority,
        opportunity_score=opportunity,
        components={
            "quality": quality,
            "relevance": relevance,
            "spam": spam,
            "authority": authority,
            "keyword_hits": float(signals.keyword_hits),
        },
        reasons=[*quality_reasons, *relevance_reasons, *spam_reasons, *authority_reasons],
        hard_rejections=find_hard_rejections(signals),
    )


def meets_thresholds(result: ScoreResult, weights: ScoringWeights | None = None) -> bool:
    """Whether a result clears the configured qualification bar."""
    active = weights or ScoringWeights()
    if result.is_rejected:
        return False
    return (
        result.quality_score >= active.min_quality_score
        and result.spam_score <= active.max_spam_score
        and result.opportunity_score >= active.min_opportunity_score
    )
