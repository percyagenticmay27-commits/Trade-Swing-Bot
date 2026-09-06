from __future__ import annotations

from datetime import date

from swing_trade_bot.discovery_engine import CandidateState, DiscoveryEngine, FinancialHealth, SourceMention
from swing_trade_bot.enterprise_discovery_bucket import bucket_mentions_with_audit, merge_mentions
from swing_trade_bot.enterprise_evidence_normalization import normalize_enterprise_source


def _bucket(*sources: dict) -> dict:
    return {
        "schema_version": "1.0",
        "strategy_id": "SWING-001",
        "candidates": [
            {
                "underlying_symbol": "NVDA",
                "discovery_status": "RISING",
                "themes": ["AI Infrastructure"],
                "evidence_sources": list(sources),
            }
        ],
    }


def _health() -> dict[str, FinancialHealth]:
    return {
        "NVDA": FinancialHealth(
            revenue_growth=80,
            eps_growth=80,
            operating_cash_flow=80,
            gross_margin_trend=80,
            debt_health=80,
            analyst_revisions=80,
            sector_strength=80,
        )
    }


def test_valid_ai_cio_source_class_has_priority_and_preserves_original_source() -> None:
    bucket = _bucket(
        {
            "source": "Custom Financial Desk",
            "source_class": "INSTITUTIONAL_FINANCIAL_NEWS",
            "mentioned_on": "2026-08-18",
        }
    )
    mentions, audit, warnings = bucket_mentions_with_audit(bucket)
    assert warnings == []
    assert len(mentions) == 1
    mention = mentions[0]
    assert mention.source == "Custom Financial Desk"
    assert mention.original_source == "Custom Financial Desk"
    assert mention.source_class == "INSTITUTIONAL_NEWS"
    assert audit[0]["normalization_method"] == "AI_CIO_SOURCE_CLASS"
    assert audit[0]["trusted_weight"] == 3


def test_known_alias_is_normalized_when_source_class_is_missing() -> None:
    result = normalize_enterprise_source("SEC EDGAR Daily Index")
    assert result.accepted is True
    assert result.source_class == "PRIMARY_REGULATORY"
    assert result.normalization_method == "SWING_ALIAS_MAP"


def test_requested_enterprise_aliases_are_recognized_deterministically() -> None:
    expected = {
        "Let's Talk Money! with Joseph Hogue, CFA": "PROFESSIONAL_CREATOR",
        "Stock Titan": "PROFESSIONAL_RESEARCH",
        "Yahoo Finance": "PROFESSIONAL_RESEARCH",
        "The Globe and Mail": "INSTITUTIONAL_NEWS",
        "MedTech Dive": "PROFESSIONAL_RESEARCH",
        "TradingView": "MARKET_ANALYTICS",
    }
    for source, source_class in expected.items():
        row = normalize_enterprise_source(source)
        assert row.accepted is True
        assert row.source_class == source_class


def test_duplicate_enterprise_evidence_does_not_inflate_runtime_mentions() -> None:
    evidence = {
        "source": "Yahoo Finance",
        "mentioned_on": "2026-08-18",
    }
    mentions, audit, warnings = bucket_mentions_with_audit(_bucket(evidence, dict(evidence)))
    assert warnings == []
    assert len(mentions) == 1
    assert sum(row.get("duplicate") is True for row in audit) == 1


def test_unknown_source_is_rejected_without_trusted_weight() -> None:
    mentions, audit, warnings = bucket_mentions_with_audit(
        _bucket({"source": "Unknown Hype Feed", "mentioned_on": "2026-08-18"})
    )
    assert mentions == []
    assert audit[0]["accepted"] is False
    assert any(item.startswith("UNRECOGNIZED_ENTERPRISE_SOURCE:") for item in warnings)


def test_invalid_supplied_source_class_fails_safe_even_for_known_display_alias() -> None:
    mentions, audit, warnings = bucket_mentions_with_audit(
        _bucket(
            {
                "source": "Reuters",
                "source_class": "TOTALLY_TRUSTED_BECAUSE_I_SAID_SO",
                "mentioned_on": "2026-08-18",
            }
        )
    )
    assert mentions == []
    assert audit[0]["accepted"] is False
    assert any("UNRECOGNIZED_ENTERPRISE_SOURCE_CLASS" in item for item in warnings)


def test_missing_source_is_rejected_as_malformed() -> None:
    mentions, audit, warnings = bucket_mentions_with_audit(
        _bucket({"source_class": "INSTITUTIONAL_NEWS", "mentioned_on": "2026-08-18"})
    )
    assert mentions == []
    assert audit[0]["accepted"] is False
    assert "MALFORMED_ENTERPRISE_SOURCE:MISSING_SOURCE" in warnings


def test_social_class_remains_visible_but_cannot_inflate_confluence() -> None:
    bucket = _bucket(
        {
            "source": "Stocktwits",
            "source_class": "SOCIAL_COMMUNITY",
            "mentioned_on": "2026-08-18",
        },
        {
            "source": "Unknown Social Clone",
            "source_class": "SOCIAL_COMMUNITY",
            "mentioned_on": "2026-08-18",
        },
    )
    mentions, _, _ = bucket_mentions_with_audit(bucket)
    assert len(mentions) == 2
    row = DiscoveryEngine(paper_trade_mode=True).evaluate(
        [CandidateState("NVDA", "NVDX")],
        mentions,
        _health(),
        as_of=date(2026, 8, 18),
    )[0]
    assert row.source_count == 0
    assert row.source_confluence_score == 0
    assert row.watchlist_status == "DISCOVERY"


def test_two_enterprise_sources_in_same_class_remain_independent_by_original_source() -> None:
    bucket = _bucket(
        {
            "source": "Reuters",
            "source_class": "INSTITUTIONAL_NEWS",
            "mentioned_on": "2026-08-18",
        },
        {
            "source": "Bloomberg",
            "source_class": "INSTITUTIONAL_NEWS",
            "mentioned_on": "2026-08-18",
        },
    )
    mentions, _, _ = bucket_mentions_with_audit(bucket)
    row = DiscoveryEngine(paper_trade_mode=True).evaluate(
        [CandidateState("NVDA", "NVDX")],
        mentions,
        _health(),
        as_of=date(2026, 8, 18),
    )[0]
    assert row.source_count == 2
    assert row.institutional_source_count == 2
    assert row.source_confluence_score == 6
    assert row.watchlist_status == "WATCHLIST"


def test_legacy_literal_source_semantics_are_unchanged() -> None:
    legacy = [
        SourceMention("NVDA", "Reuters", date(2026, 8, 18)),
        SourceMention("NVDA", "Bow Tie Nation", date(2026, 8, 18)),
    ]
    row = DiscoveryEngine(paper_trade_mode=True).evaluate(
        [CandidateState("NVDA", "NVDX")],
        legacy,
        _health(),
        as_of=date(2026, 8, 18),
    )[0]
    assert row.source_count == 2
    assert row.institutional_source_count == 1
    assert row.youtube_source_count == 1
    assert row.source_confluence_score == 4


def test_local_and_enterprise_duplicate_source_date_merge_without_inflation() -> None:
    local = SourceMention("NVDA", "Reuters", date(2026, 8, 18))
    enterprise = SourceMention(
        "NVDA",
        "Reuters",
        date(2026, 8, 18),
        source_class="INSTITUTIONAL_NEWS",
        original_source="Reuters",
    )
    merged = merge_mentions([local], [enterprise])
    assert merged == [local]
