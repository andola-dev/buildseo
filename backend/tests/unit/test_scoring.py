"""Publisher qualification scoring."""

from __future__ import annotations

import dataclasses

import pytest

from app.publishers.scoring import (
    PublisherSignals,
    ScoringWeights,
    meets_thresholds,
    score_publisher,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def excellent() -> PublisherSignals:
    return PublisherSignals(
        reachable=True,
        http_status=200,
        tls_valid=True,
        has_submission_path=True,
        is_free=True,
        indexable=True,
        keyword_hits=4,
        keywords_considered=5,
        category_match=True,
        country_match=True,
        language_match=True,
        authority_score=72.0,
        organic_traffic=50_000,
        outbound_links=120,
    )


@pytest.fixture
def decent() -> PublisherSignals:
    return PublisherSignals(
        reachable=True,
        tls_valid=True,
        has_submission_path=True,
        is_free=True,
        indexable=True,
        keyword_hits=3,
        keywords_considered=3,
        category_match=True,
        country_match=True,
        language_match=True,
        authority_score=60.0,
    )


class TestComponentScores:
    def test_a_perfect_free_directory_scores_full_quality(
        self, excellent: PublisherSignals
    ) -> None:
        result = score_publisher(excellent)
        assert result.quality_score == 100.0
        assert result.relevance_score == 88.0  # 4*12 + 20 + 12 + 8
        assert result.spam_score == 0.0
        assert result.authority_score == 72.0
        assert not result.is_rejected
        assert meets_thresholds(result)

    def test_component_breakdown_is_returned_with_the_score(
        self, excellent: PublisherSignals
    ) -> None:
        # Users have to trust a score, so the parts and reasons come with it.
        result = score_publisher(excellent)
        assert set(result.components) == {
            "quality",
            "relevance",
            "spam",
            "authority",
            "keyword_hits",
        }

    def test_missing_evidence_lowers_the_score_with_a_reason(self) -> None:
        result = score_publisher(
            PublisherSignals(reachable=True, has_submission_path=True, is_free=True)
        )
        assert result.quality_score < 100.0
        assert any("HTTPS" in reason for reason in result.reasons)


class TestHardRejections:
    def test_an_unreachable_site_is_rejected_however_good_it_looks(self) -> None:
        result = score_publisher(
            PublisherSignals(
                reachable=False,
                has_submission_path=True,
                is_free=True,
                keyword_hits=5,
                authority_score=99,
            )
        )
        assert "unreachable" in result.hard_rejections
        assert not meets_thresholds(result)

    def test_a_paid_only_directory_is_rejected_however_good_it_looks(self) -> None:
        # The platform's core rule: no combination of other signals lets a paid
        # placement through.
        result = score_publisher(
            PublisherSignals(
                reachable=True,
                tls_valid=True,
                has_submission_path=True,
                is_free=False,
                is_paid_only=True,
                indexable=True,
                keyword_hits=5,
                keywords_considered=5,
                category_match=True,
                country_match=True,
                language_match=True,
                authority_score=95,
            )
        )
        assert "paid_only" in result.hard_rejections
        assert not meets_thresholds(result)
        assert any("payment" in reason for reason in result.reasons)

    def test_no_submission_path_is_rejected(self) -> None:
        result = score_publisher(
            PublisherSignals(
                reachable=True,
                tls_valid=True,
                is_free=True,
                has_submission_path=False,
                indexable=True,
            )
        )
        assert "no_submission_path" in result.hard_rejections

    @pytest.mark.parametrize("signal", ["paid_links_offered", "link_scheme", "pbn_footprint"])
    def test_link_scheme_signals_are_rejected(self, signal: str) -> None:
        result = score_publisher(
            PublisherSignals(
                reachable=True,
                tls_valid=True,
                is_free=True,
                has_submission_path=True,
                indexable=True,
                spam_signals=(signal,),
            )
        )
        assert "link_scheme_detected" in result.hard_rejections
        assert any(signal.replace("_", " ") in reason for reason in result.reasons)


class TestSpamPenalty:
    def test_spam_signals_reduce_the_opportunity_score(self, decent: PublisherSignals) -> None:
        clean = score_publisher(decent)
        spammy = score_publisher(
            dataclasses.replace(decent, spam_signals=("adult_content", "cloaking"))
        )
        assert clean.spam_score == 0.0
        assert spammy.spam_score == 44.0
        assert spammy.opportunity_score < clean.opportunity_score

    def test_enough_spam_pushes_a_site_below_the_threshold(self, decent: PublisherSignals) -> None:
        result = score_publisher(dataclasses.replace(decent, spam_signals=("a", "b", "c")))
        assert result.spam_score == 66.0
        assert not meets_thresholds(result)

    def test_a_wall_of_outbound_links_reads_as_a_link_farm(self, decent: PublisherSignals) -> None:
        result = score_publisher(dataclasses.replace(decent, outbound_links=900))
        assert result.spam_score == 18.0
        assert any("outbound link" in reason for reason in result.reasons)

    def test_a_normal_link_count_is_not_penalised(self, decent: PublisherSignals) -> None:
        assert score_publisher(dataclasses.replace(decent, outbound_links=250)).spam_score == 0.0


class TestUnknownAuthority:
    def test_unmeasured_authority_scores_neutral_not_zero(self, decent: PublisherSignals) -> None:
        # A workspace with no SEO-metrics subscription must still be able to
        # qualify publishers, so absent data must not reject everything.
        result = score_publisher(dataclasses.replace(decent, authority_score=None))
        assert result.authority_score == 50.0
        assert any("Authority unknown" in reason for reason in result.reasons)
        assert meets_thresholds(result)


class TestClamping:
    def test_scores_stay_within_the_database_check_range(self, decent: PublisherSignals) -> None:
        extreme = ScoringWeights(
            keyword_match_points=500, max_keyword_points=5_000, spam_signal_points=500
        )
        result = score_publisher(
            dataclasses.replace(decent, keyword_hits=99, spam_signals=("x",) * 10), extreme
        )
        for value in (
            result.quality_score,
            result.relevance_score,
            result.spam_score,
            result.authority_score,
            result.opportunity_score,
        ):
            assert 0.0 <= value <= 100.0


class TestConfigurableWeights:
    def test_weights_load_defensively_from_tenant_settings(self) -> None:
        weights = ScoringWeights.from_mapping(
            {
                "quality_weight": 0.8,
                "unknown_key": 1,
                "spam_weight": "not-a-number",
                "relevance_weight": True,
            }
        )
        assert weights.quality_weight == 0.8
        # Unknown keys, non-numeric values and booleans are ignored rather than
        # crashing a request or silently distorting the model.
        assert weights.spam_weight == ScoringWeights().spam_weight
        assert weights.relevance_weight == ScoringWeights().relevance_weight

    def test_absent_settings_use_the_defaults(self) -> None:
        assert ScoringWeights.from_mapping(None) == ScoringWeights()
        assert ScoringWeights.from_mapping({}) == ScoringWeights()

    def test_weighting_relevance_higher_changes_the_ranking(self, decent: PublisherSignals) -> None:
        irrelevant = dataclasses.replace(
            decent,
            keyword_hits=0,
            keywords_considered=5,
            category_match=False,
            country_match=False,
            language_match=False,
        )
        relevance_heavy = ScoringWeights(
            quality_weight=0.1, relevance_weight=0.8, authority_weight=0.1
        )
        assert (
            score_publisher(irrelevant, relevance_heavy).opportunity_score
            < score_publisher(irrelevant).opportunity_score
        )

    def test_zero_positive_weight_mass_is_rejected(self, excellent: PublisherSignals) -> None:
        with pytest.raises(ValueError, match="positive"):
            score_publisher(
                excellent,
                ScoringWeights(quality_weight=0, relevance_weight=0, authority_weight=0),
            )


class TestSignalSerialisation:
    def test_signals_round_trip_to_a_storable_dict(self, excellent: PublisherSignals) -> None:
        stored = excellent.to_dict()
        assert stored["spam_signals"] == []
        assert stored["keyword_hits"] == 4
        assert stored["is_free"] is True
